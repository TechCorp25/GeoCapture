"""On-demand street metadata suggestions. Never replaces surveyed bay coordinates."""
import json
import logging
import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROAD_TYPES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "road", "track",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
QUERY_RADIUS = 800
WALK_RADIUS = 700  # Keep endpoints inside the fully queried neighbourhood.
ATTRIBUTION = {"source": "OpenStreetMap", "attribution": "© OpenStreetMap contributors",
               "license": "ODbL-1.0", "url": "https://www.openstreetmap.org/copyright"}
_slots = threading.BoundedSemaphore(2)
_limit_lock = threading.Lock()
_requests = deque()
# Short-lived process-local OSM geometry cache. No raw network data or GPS
# positions are persisted to disk or MongoDB by this metadata service.
_network_cache = deque(maxlen=8)
_network_cache_lock = threading.Lock()
_provider_backoff = {}
_provider_backoff_lock = threading.Lock()
CACHE_TTL_SECONDS = 600
PROVIDER_BACKOFF_SECONDS = 120
ALL_PROVIDERS_RETRY_SECONDS = 10
PROVIDER_TIMEOUT_SECONDS = 12


class LookupUnavailable(Exception):
    pass


class LookupBusy(LookupUnavailable):
    pass


def config():
    return {
        "enabled": os.environ.get("STREET_LOOKUP_ENABLED", "false").lower() == "true",
        "googleReferenceEnabled": bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()),
    }


def validate_request(payload):
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")
    values = []
    for key, lower, upper in (("latitude", -90, 90), ("longitude", -180, 180), ("accuracy", 0, 25)):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number.")
        if not lower <= value <= upper or (key == "accuracy" and value == 0):
            raise ValueError(f"{key} is outside the supported range. Use a fresh GPS fix within ±25 m.")
        values.append(value)
    street = payload.get("street", "")
    if not isinstance(street, str) or len(street) > 150:
        raise ValueError("street must be text of at most 150 characters.")
    validate_locality(payload)
    return (*values, street.strip())


def validate_locality(payload):
    suburb = payload.get("suburb")
    postcode = payload.get("postcode")
    if suburb is not None and (not isinstance(suburb, str) or len(suburb) > 100):
        raise ValueError("Suburb must be text of at most 100 characters.")
    if postcode is not None and (not isinstance(postcode, str) or
                                 (postcode.strip() and not re.fullmatch(r"[0-9]{4}", postcode.strip()))):
        raise ValueError("Enter a four-digit postcode.")
    return (suburb or "").strip().upper(), (postcode or "").strip()


def locality_warnings(elements, suburb, postcode):
    # Only enclosing areas describe the GPS fix. Nearby road address tags can
    # belong to another suburb, so they must not validate the capture locality.
    areas = [e.get("tags", {}) for e in elements if e.get("type") == "area"]
    suburbs, postcodes = set(), set()
    for tags in areas:
        if tags.get("place") in {"suburb", "town", "village", "locality", "neighbourhood"} or tags.get("admin_level") == "10":
            for key in ("name", "official_name", "alt_name", "short_name"):
                suburbs.update(v.strip().upper() for v in tags.get(key, "").split(";") if v.strip())
        for key in ("postal_code", "addr:postcode"):
            postcodes.update(v.strip() for v in tags.get(key, "").split(";") if v.strip())
    warnings = []
    for label, value, known in (("Suburb", suburb, suburbs), ("Postcode", postcode, postcodes)):
        if value and known and value not in known:
            raise LookupUnavailable(f"{label} does not match the GPS locality. Check the field or your location and retry.")
        if value and not known:
            warnings.append(f"{label} unavailable in map data; streets use GPS only.")
    return warnings


def normalise(name):
    name = re.sub(r"[.]+", "", name.strip().upper())
    name = re.sub(r"\s+", " ", name)
    # Expand only a suffix, so names such as ST KILDA ROAD are preserved.
    parts = name.split(" ")
    parts[-1] = {"ST": "STREET", "RD": "ROAD", "AVE": "AVENUE", "CT": "COURT",
                 "CRES": "CRESCENT", "DR": "DRIVE", "PL": "PLACE", "LN": "LANE",
                 "PDE": "PARADE", "HWY": "HIGHWAY", "TCE": "TERRACE"}.get(parts[-1], parts[-1])
    return " ".join(parts)


def fetch_json(request, timeout=15):
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(6_000_001)
        if len(raw) > 6_000_000:
            raise ValueError("Response too large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Unexpected response")
        return data
    except HTTPError as exc:
        logging.warning("Street provider request failed: HTTP %s", exc.code)
        raise LookupUnavailable(f"Location provider returned HTTP {exc.code}. Enter the street details manually or retry later.") from None
    except (TimeoutError, URLError) as exc:
        # Exception text / URLs may include keys and coordinates. Log only
        # exception classes and numeric system codes to diagnose DNS/TLS failures.
        reason = exc.reason if isinstance(exc, URLError) else exc
        error_number = getattr(reason, "errno", None)
        verify_code = getattr(reason, "verify_code", None)
        logging.warning("Street provider connection failed: %s reason=%s errno=%s tls_code=%s",
                        type(exc).__name__, type(reason).__name__,
                        error_number if isinstance(error_number, int) else None,
                        verify_code if isinstance(verify_code, int) else None)
        raise LookupUnavailable("Location provider connection failed or timed out. Enter the street details manually or retry.") from None
    except Exception as exc:
        logging.warning("Street provider response failed: %s", type(exc).__name__)
        # Provider errors may contain the API key or location. Do not surface them.
        raise LookupUnavailable("Location provider is unavailable. Enter the street details manually or retry.") from None


def road_network(lat, lon, include_locality=False):
    # Re-resolve cached road geometry against EACH new GPS coordinate. Never
    # cache a street label or boundary result that might become stale.
    now = time.monotonic()
    with _network_cache_lock:
        while _network_cache and now - _network_cache[0][0] > CACHE_TTL_SECONDS:
            _network_cache.popleft()
        for stamp, centre_lat, centre_lon, area, elements in reversed(_network_cache):
            metres = math.hypot((lat - centre_lat) * 111320,
                                (lon - centre_lon) * 111320 * math.cos(math.radians(lat)))
            if area == include_locality and metres <= (15 if include_locality else 40):
                return elements
    # All ways touching seed nodes are included, preventing artificial dead ends
    # at OSM way splits. Names never enter this query (no query injection).
    road_filter = '[highway~"^(' + "|".join(sorted(ROAD_TYPES)) + ')$"]'
    neighbourhood = f"(around:{QUERY_RADIUS},{lat:.7f},{lon:.7f})"
    # An OSM way can extend kilometres outside the search area. Expand junctions
    # only at nearby nodes, rather than fetching neighbours along its full length.
    query = (f"[out:json][timeout:15][maxsize:67108864];way{neighbourhood}{road_filter}->.roads;"
             f"node(w.roads){neighbourhood}->.nodes;way(bn.nodes){road_filter}->.connected;"
             "(.roads;.connected;);out body;>;out skel qt;")
    if include_locality:
        query += f"is_in({lat:.7f},{lon:.7f});out tags;"
    endpoint = os.environ.get("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")
    if not endpoint.startswith("https://"):
        raise LookupUnavailable("The road-network provider requires an HTTPS endpoint.")
    # Keep the operator's endpoint first, but do not let a single provider
    # outage disable capture metadata. Empty fallback explicitly disables it.
    fallback = os.environ.get(
        "OVERPASS_FALLBACK_URL", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ).strip()
    if fallback and not fallback.startswith("https://"):
        raise LookupUnavailable("The fallback road provider requires an HTTPS endpoint.")
    endpoints = list(dict.fromkeys(url for url in (endpoint, fallback) if url))
    for index, url in enumerate(endpoints):
        with _provider_backoff_lock:
            if _provider_backoff.get(url, 0) > time.monotonic():
                continue
        try:
            headers = {"User-Agent": "GeoCapture/1.0 https://github.com/TechCorp25/GeoCapture",
                       "Content-Type": "application/x-www-form-urlencoded"}
            encoded = urlencode({"data": query})
            # Both providers support GET. POST has repeatedly failed from the
            # deployed host while the identical GET query succeeds. The browser
            # API remains POST; never log this upstream URL or its coordinates.
            request = Request(url + ("&" if "?" in url else "?") + encoded, headers=headers)
            data = fetch_json(request, timeout=PROVIDER_TIMEOUT_SECONDS)
            if data.get("remark") or not isinstance(data.get("elements"), list):
                raise LookupUnavailable("Incomplete road-network response.")
            elements = data["elements"]
            with _provider_backoff_lock:
                _provider_backoff.pop(url, None)
            with _network_cache_lock:
                _network_cache.append((time.monotonic(), lat, lon, include_locality, elements))
            return elements
        except LookupUnavailable:
            # Do not spend several more seconds re-trying an unhealthy primary
            # provider for every subsequent operator lookup.
            with _provider_backoff_lock:
                _provider_backoff[url] = time.monotonic() + PROVIDER_BACKOFF_SECONDS
            logging.warning("Street provider attempt %s failed", index + 1)
    # A healthy fallback still shields a failed primary for two minutes. When
    # every provider fails, permit recovery after a short pause instead of
    # making every user retry fail without contacting either provider. Do not
    # extend an existing deadline when requests arrive during the pause.
    with _provider_backoff_lock:
        retry_at = time.monotonic() + ALL_PROVIDERS_RETRY_SECONDS
        for url in endpoints:
            _provider_backoff[url] = min(_provider_backoff.get(url, retry_at), retry_at)
    raise LookupUnavailable("Street providers unavailable. Retry lookup in 10 seconds.")



def google_reference(lat, lon):
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        return None
    params = urlencode({"latlng": f"{lat},{lon}", "key": key, "language": "en", "result_type": "route"})
    data = fetch_json(Request("https://maps.googleapis.com/maps/api/geocode/json?" + params), timeout=8)
    if data.get("status") == "ZERO_RESULTS":
        return None
    if data.get("status") != "OK":
        raise LookupUnavailable("Google street reference is unavailable.")
    for result in data.get("results", []):
        for component in result.get("address_components", []):
            if "route" in component.get("types", []) and isinstance(component.get("long_name"), str):
                return component["long_name"][:150]
    return None


def resolve_network(elements, lat, lon, accuracy, street=""):
    nodes = {e["id"]: e for e in elements if e.get("type") == "node" and "lat" in e and "lon" in e}
    ways = {e["id"]: e for e in elements if e.get("type") == "way"
            and e.get("tags", {}).get("highway") in ROAD_TYPES}
    if any(n not in nodes for way in ways.values() for n in way.get("nodes", [])):
        raise LookupUnavailable("Road geometry is incomplete. Enter boundaries manually or retry.")
    graph = defaultdict(list)
    xy = {key: ((node["lon"] - lon) * 111320 * math.cos(math.radians(lat)),
                (node["lat"] - lat) * 111320) for key, node in nodes.items()}
    candidates = []

    def name(way_id):
        return normalise(ways[way_id].get("tags", {}).get("name", ""))

    def minor(way_id):
        tags = ways[way_id].get("tags", {})
        return tags.get("service") in {"driveway", "parking_aisle"} or tags.get("access") == "private"

    for way_id, way in ways.items():
        for a, b in zip(way.get("nodes", []), way.get("nodes", [])[1:]):
            if a not in xy or b not in xy or a == b:
                continue
            graph[a].append((b, way_id))
            graph[b].append((a, way_id))
            ax, ay = xy[a]
            bx, by = xy[b]
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            if not length2 or not name(way_id) or minor(way_id):
                continue
            t = max(0, min(1, -(ax * dx + ay * dy) / length2))
            distance = math.hypot(ax + t * dx, ay + t * dy)
            if distance <= 40:
                candidates.append((distance, way_id, a, b))
    candidates.sort()
    nearby = list(dict.fromkeys(name(c[1]) for c in candidates))[:6]
    result = {"street": None, "between": [None, None], "candidates": nearby,
              "warnings": [], "attribution": ATTRIBUTION.copy()}
    if street:
        candidates = [c for c in candidates if name(c[1]) == normalise(street)]
    if not candidates:
        result["warnings"].append("No matching named road within 40 m. Enter or correct the street manually.")
        return result
    best = candidates[0]
    selected_name = name(best[1])
    if not street and any(name(c[1]) != selected_name and c[0] <= best[0] + accuracy + 3 for c in candidates[1:]):
        result["warnings"].append("Several streets are close to this fix. Enter the correct street and look up again.")
        return result
    result["street"] = selected_name
    if ways[best[1]].get("tags", {}).get("junction") == "roundabout":
        result["warnings"].append("Roundabout boundaries need manual review.")
        return result

    def walk(start, previous):
        visited = {previous}
        current = start
        for _ in range(2000):
            if current in visited:
                return None, "A road loop needs manual boundary entry."
            visited.add(current)
            if math.hypot(*xy[current]) > WALK_RADIUS:
                return None, "A boundary lies outside the lookup area; enter it manually."
            edges = graph[current]
            if any(ways[w].get("tags", {}).get("junction") == "roundabout" for _, w in edges):
                return None, "A roundabout needs manual boundary entry."
            cross = {name(w) for _, w in edges if name(w) and name(w) != selected_name and not minor(w)}
            if cross:
                if math.hypot(*xy[current]) <= accuracy + 5:
                    return None, "You are close to an intersection. Move into the segment and retry, or enter its boundaries."
                if len(cross) == 1:
                    return next(iter(cross)), None
                return None, "Several roads meet at a boundary; enter the applicable street manually."
            onward = {(n, w) for n, w in edges if n != previous and name(w) == selected_name}
            if not onward:
                if len({n for n, _ in edges}) == 1:
                    return "DEAD END", "Check the suggested dead end on site; map data can be incomplete."
                return None, "An unnamed road or road-name change needs manual boundary entry."
            if len(onward) != 1:
                return None, "The street branches here; enter the boundary manually."
            # Do not step past an unnamed public road and imply a longer segment.
            if any(not name(w) and not minor(w) for _, w in edges):
                return None, "An unnamed intersecting road needs manual boundary entry."
            previous, (current, _) = current, next(iter(onward))
        return None, "The road is too complex for automatic boundary lookup."

    # Guard same-name split carriageways / blocks near the fix, not just names.
    if any(c[1] != best[1] and not {c[2], c[3]} & {best[2], best[3]}
           and c[0] <= best[0] + accuracy + 3 for c in candidates[1:]):
        result["warnings"].append("Parallel or nearby road sections are ambiguous. Enter the boundaries manually.")
        return result
    for i, (start, previous) in enumerate(((best[2], best[3]), (best[3], best[2]))):
        result["between"][i], warning = walk(start, previous)
        if warning and warning not in result["warnings"]:
            result["warnings"].append(warning)
    return result


def lookup(payload):
    lat, lon, accuracy, street = validate_request(payload)
    if not config()["enabled"]:
        raise LookupUnavailable("Street lookup is disabled. Enter the details manually.")
    if not _slots.acquire(blocking=False):
        raise LookupBusy("Street lookup is busy. Please retry shortly.")
    try:
        now = time.monotonic()
        with _limit_lock:
            while _requests and _requests[0] < now - 86400:
                _requests.popleft()
            if len(_requests) >= 1000 or sum(t > now - 60 for t in _requests) >= 30:
                raise LookupBusy("Street lookup limit reached. Enter details manually or retry later.")
            _requests.append(now)
        suburb, postcode = validate_locality(payload)
        elements = road_network(lat, lon, include_locality=bool(suburb or postcode))
        warnings = locality_warnings(elements, suburb, postcode)
        result = resolve_network(elements, lat, lon, accuracy, street)
        result["warnings"].extend(warnings)
        # Google's result is display-only and never feeds the saved OSM labels.
        try:
            result["googleReference"] = google_reference(lat, lon)
        except LookupUnavailable:
            result["googleReference"] = None
            result["warnings"].append("Google reference unavailable; road-network suggestions are still available.")
        return result
    finally:
        _slots.release()
