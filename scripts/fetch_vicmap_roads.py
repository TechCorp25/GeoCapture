#!/usr/bin/env python3
"""Fetch a bounded, reproducible snapshot of official Vicmap Transport TR_ROAD.

This tool executes at build time only. GeoCapture devices never contact Vicmap.
ArcGIS endpoint and fields independently checked against official service docs.
All raw records remain REVIEW CANDIDATES until topology and field QA complete.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

LAYER = "https://vicmap.land.vic.gov.au/agsgis/rest/services/vicmap/Vicmap_Transport/MapServer/1/query"
ATTRS = "id,ufi,pfi,ezi_road_name,road_name,road_type,left_locality,right_locality,from_ufi,to_ufi,feature_type_code,class_code,structure_name,road_status,vehicular_access"
# Wide Footscray staging bounds, not an authoritative LGA polygon.
DEFAULT_BBOX = (144.87, -37.835, 144.945, -37.785)
PAGE_SIZE = 500
AGENT = "GeoCapture engineering road-index builder (offline source acquisition; contact via project repository)"

def fetch_page(params, tries=3):
    url = LAYER + "?" + urllib.parse.urlencode(params, safe=",")
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=35) as response:
                data = response.read(18_000_000 + 1)
                if len(data) > 18_000_000:
                    raise ValueError("Unexpectedly large ArcGIS response")
                doc = json.loads(data)
                if isinstance(doc, dict) and doc.get("error"):
                    raise ValueError("Vicmap ArcGIS query error: " + str(doc["error"]))
                return doc
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            if attempt == tries - 1:
                raise RuntimeError("Official Vicmap service unavailable") from error
            time.sleep(2 ** attempt)

def collect(bbox, max_features=12000):
    min_x, min_y, max_x, max_y = bbox
    if not (143 < min_x < max_x < 146 and -39 < min_y < max_y < -36):
        raise ValueError("Expected bounded Melbourne-area WGS84 bbox")
    base = {
        "where": "1=1", "geometry": ",".join(map(str, bbox)),
        "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ATTRS, "returnGeometry": "true",
        "outSR": 4326, "f": "geojson",
    }
    features_by_id = {}
    offset = 0
    while True:
        doc = fetch_page({**base, "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
                          "orderByFields": "id ASC"})
        if doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
            raise ValueError("Vicmap did not return a GeoJSON FeatureCollection")
        batch = doc["features"]
        if not batch:
            break
        for item in batch:
            p = item.get("properties") or {}
            identifier = p.get("pfi") or p.get("ufi") or p.get("id") or item.get("id")
            if identifier is not None:
                features_by_id[str(identifier)] = item
        offset += len(batch)
        if len(features_by_id) > max_features:
            raise ValueError("Road-snapshot extent too broad; reduce bbox and retry")
        if len(batch) < PAGE_SIZE and not doc.get("exceededTransferLimit"):
            break
        if offset > max_features + PAGE_SIZE:
            raise ValueError("Pagination exhausted capacity; refusing truncated snapshot")
    if not features_by_id:
        raise ValueError("No features returned; refusing to publish empty snapshot")
    records = sorted(features_by_id.values(), key=lambda x: str(
        (x.get("properties") or {}).get("pfi") or x.get("id") or ""))
    return {"type": "FeatureCollection", "features": records}


def polygon_bounds(boundary_geometry, buffer_metres=600):
    """Use official LGA polygon for acquisition extent; buffer protects junctions."""
    if boundary_geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("Expected official LGA Polygon/MultiPolygon")
    if not 100 <= buffer_metres <= 2000:
        raise ValueError("Municipal buffer must be between 100 and 2000 metres")
    polygons = ([boundary_geometry["coordinates"]] if boundary_geometry["type"] == "Polygon"
                else boundary_geometry["coordinates"])
    points = [point for poly in polygons for ring in poly for point in ring]
    if not points or any(len(p) < 2 or not all(isinstance(v, (int, float)) and
                        __import__("math").isfinite(v) for v in p[:2]) for p in points):
        raise ValueError("Invalid official LGA polygon coordinates")
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    import math
    midlat = (south + north) / 2
    latbuffer = buffer_metres / 111000
    lonbuffer = buffer_metres / (111000 * math.cos(math.radians(midlat)))
    return (west - lonbuffer, south - latbuffer, east + lonbuffer, north + latbuffer)


def collect_municipality(boundary_geometry, buffer_metres=600, max_features=65000):
    """Retrieve all IDs twice around paged fetch to fail on gaps/source drift.

    Envelope is ONLY the source acquisition extent. Legal municipality
    membership is determined separately from the original official polygon.
    """
    bbox = polygon_bounds(boundary_geometry, buffer_metres)
    query = {"where": "1=1", "geometry": ",".join(map(str, bbox)),
             "geometryType": "esriGeometryEnvelope", "inSR": 4326,
             "spatialRel": "esriSpatialRelIntersects",
             "returnIdsOnly": "true", "f": "json"}
    def official_ids():
        result = fetch_page(query)
        ids = result.get("objectIds")
        if not isinstance(ids, list) or not ids:
            raise ValueError("Official ArcGIS object ID inventory absent or empty")
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate ArcGIS object identifiers")
        if len(ids) > max_features:
            raise ValueError("Municipal extent exceeds configured snapshot capacity")
        return set(ids)
    before = official_ids()
    snapshot = collect(bbox, max_features=max_features)
    actual = [f.get("properties", {}).get("id", f.get("id")) for f in snapshot["features"]]
    if len(actual) != len(set(actual)) or None in actual:
        raise ValueError("Duplicate or absent official ArcGIS road object IDs")
    if before != set(actual):
        raise ValueError("Incomplete ArcGIS pagination or mismatch with official ID inventory")
    if before != official_ids():
        raise ValueError("Official road source changed during acquisition")
    pfis = [f.get("properties", {}).get("pfi") for f in snapshot["features"]]
    if None in pfis or len(pfis) != len(set(map(str, pfis))):
        raise ValueError("Missing or duplicate official Vicmap PFI; review required")
    return snapshot, {"bboxWGS84": bbox, "bufferMetres": buffer_metres,
                      "officialObjectIdCount": len(before),
                      "receivedObjectIdCount": len(actual),
                      "paginationVerified": True,
                      "queryExtentBasis": "official_LGA_polygon_bounds_plus_junction_buffer",
                      "municipalityScope": "MARIBYRNONG"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bbox", nargs=4, type=float, default=list(DEFAULT_BBOX))
    parser.add_argument("--boundary", help="Verified official Maribyrnong LGA GeoJSON")
    parser.add_argument("--boundary-manifest", help="Checksum manifest for official LGA")
    parser.add_argument("--buffer-metres", type=int, default=600)
    args = parser.parse_args()
    if bool(args.boundary) != bool(args.boundary_manifest):
        parser.error("--boundary and --boundary-manifest are required together")
    bbox = tuple(args.bbox)
    metadata = {}
    if args.boundary:
        from scripts.audit_municipal_candidates import validate_boundary
        raw = pathlib.Path(args.boundary).read_bytes()
        geometry = validate_boundary(json.loads(raw),
                   json.loads(pathlib.Path(args.boundary_manifest).read_text()), raw)
        doc, metadata = collect_municipality(geometry, args.buffer_metres)
        bbox = metadata["bboxWGS84"]
    else:
        doc = collect(bbox)
    dest = pathlib.Path(args.output); dest.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(doc, separators=(",", ":"), ensure_ascii=False)+"\n").encode("utf-8")
    dest.write_bytes(encoded)
    manifest = {
        "source": "Vicmap Transport TR_ROAD (Department of Transport and Planning, Victoria)",
        "serviceUrl": LAYER, "licence": "CC BY 4.0",
        "licenceUrl": "https://creativecommons.org/licenses/by/4.0/",
        "retrievedUTC": dt.datetime.now(dt.timezone.utc).isoformat(),
        "bboxWGS84": bbox, "featureCount": len(doc["features"]),
        **metadata,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "reviewStatus": "UNVERIFIED_CANDIDATE_NOT_FOR_PRODUCTION",
        "note": ("Authoritative polygon used for municipal scope; bounding envelope plus "
                 "buffer is acquisition-only; separately clip/classify to the LGA" if args.boundary
                 else "Bbox is a Footscray study area, not a legally accurate council boundary."),
    }
    pathlib.Path(args.manifest).write_text(json.dumps(manifest, indent=2)+"\n")
    print("VICMAP:",json.dumps(manifest))
if __name__ == "__main__":
    main()
