# GeoCapture

Internal CivicMAPS engineering tool for parking-bay data capture.

## Street and boundary auto-fill

GeoCapture now attempts a **local, on-device road-segment match first** using the
historic CivicMAPS Melbourne CBD grid. Successful local matches require no street
provider, API key, Render request or MongoDB connection. GPS uncertainty suppresses
unreliable street-side suggestions; intersecting/ambiguous roads require operator
verification. The primary local seed includes **146 CBD segments only**, not Footscray
or all City of Melbourne roads. Uncovered streets use the existing OSM service when
online and configured; manual fields are always editable. Lookup does not block
parking-bay capture or its separate local persistence queue.

After an operator enables lookup, tap **Auto-fill street & between streets** before capturing the first bay. The
app takes a fresh fix within ±25 m, independently of the stricter bay-capture quality gate, finds the current
street, and follows its connected road geometry in both directions to suggest
the adjoining street or `DEAD END`. Review the result against the signs on site.
The lookup does not record a bay or replace any measured bay coordinates.

All four street/side fields remain editable. Only blank fields are filled. Existing
entries, including edits or deletions made while a request is running, are kept.
Clear an entry to request a new suggestion. Editing the street removes boundaries
previously auto-filled for that street; manual boundaries are retained for review.
Leaving the street field triggers another boundary lookup if the previous GPS fix
is less than 60 seconds old. Otherwise tap auto-fill to obtain a fresh fix.
Finish & clear now clears street, boundaries and side before the next segment.
Auto-fill is unavailable once a segment contains captured bays; its metadata can
still be corrected manually. This prevents a new location changing an active survey.

### Providers and configuration

When the local index does not contain a trustworthy match, remote fallback
street/boundary names are derived from **OpenStreetMap** road topology through
Overpass. Historical local matches retain their own source attribution. A Google reverse-geocoded street is optionally
shown as a separate, transient reference. Google does not expose both adjacent
intersections or a dead-end flag through its documented Geocoding / Roads APIs.
Google data never selects the OSM road, populates form fields, enters local form
storage, or enters exported JSON / MongoDB. Enabling Google adds a reference check,
not additional boundary coverage. No Google API key is needed for auto-fill.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `STREET_LOOKUP_ENABLED` | `false` | Set `true` after approving coordinate transfer to the configured road provider. Manual entry remains available when disabled. |
| `OVERPASS_API_URL` | `https://overpass-api.de/api/interpreter` | HTTPS Overpass endpoint, supplied by the operator only. |
| `OVERPASS_FALLBACK_URL` | `https://maps.mail.ru/osm/tools/overpass/api/interpreter` | Secondary OSM provider after a failed or incomplete primary response. Set empty to disable. |
| `GOOGLE_MAPS_API_KEY` | unset | Optional server-only Geocoding API key; enables the Google street reference. |

For Google, enable the Geocoding API in a billing-enabled Google Cloud project,
restrict the key to that API and the server's allowed outbound addresses, set
provider quotas, and configure it as a Render secret. Never put it in HTML or git.
Before enabling Google in production, provide the application Terms of Use and
Privacy Policy required by Google. Google results are displayed with attribution
without a map and are not cached or saved by this application.

The operator approved OpenStreetMap lookup and production activation on 8 October
2026. The Render blueprint enables lookup; other deployments remain opt-in via
`STREET_LOOKUP_ENABLED=true`. Automated tests use synthetic road networks and
provider responses. Google is optional and requires its own configured key.

Remote fallback lookups send the requested coordinate to the primary road provider, then the fallback only on failure and, only
when its key is configured, Google. There is no background location watching,
peer sharing, or continuous upload. The GPS watcher closes when sampling finishes.
The lookup endpoint uses POST so coordinates are absent from request URLs, returns
`Cache-Control: no-store`, and is excluded from the service-worker cache. No lookup
coordinates or raw provider responses are saved by the backend. Both road providers use
HTTPS GET upstream, so each provider receives the query in the URL; application logs
do not include that URL. The default fallback is the VK Maps global OSM instance. Upstream providers
have their own request-handling policies.

OSM attribution is displayed in the form and retained in the optional additive
`segment.locationAttribution` field in v3 exports and MongoDB. Preserve that
attribution when using exported data. OSM data is licensed under ODbL; assess the
applicable attribution and share-alike obligations before distributing derived
databases. Manually collected bay coordinates remain device observations.

### Accuracy and operational limits

This is assisted metadata entry, not authoritative street surveying. The resolver
uses shared road nodes (so an unconnected overpass is not an intersection), walks
across same-name OSM way splits, and limits boundary resolution to 700 m from the
fix inside an 800 m query area. Dead ends are suggestions based on mapped road
connectivity and must be checked on site. Missing map data is not proof of a dead end.
Unnamed roads, forks, roundabouts, close parallel roads, fixes close to junctions,
incomplete responses, and boundaries outside the search area can require manual
entry. Side of street remains a manual selection. GPS accuracy is not street-name
confidence. Public Overpass availability and map completeness are not guaranteed.

The backend bounds requests to two concurrent lookups, 30 per minute and 1,000 per
day **per process**; these limits reset on restart and are not account authentication
or a billing cap. For wider public use, provide authenticated access / shared rate
limiting and a provisioned road-data service. Provider timeouts, unavailable service,
missing Google keys, and offline operation do not block manual entry or local capture.

API: `GET /api/location/config` returns public feature flags only;
`POST /api/location/suggest` accepts JSON `{latitude, longitude, accuracy, street?}`.
It returns optional `street`, two nullable `between` suggestions, nearby `candidates`,
`warnings`, OSM `attribution`, and a display-only `googleReference`. Invalid requests
return 400, oversized requests 413, non-JSON requests 415, busy/rate-limited requests
429, and disabled/unavailable providers 503. No new Python dependencies are required.

Provider documentation:

- [Google reverse geocoding](https://developers.google.com/maps/documentation/geocoding/guides-v3/requests-reverse-geocoding)
- [Google Roads: Nearest Roads response](https://developers.google.com/maps/documentation/roads/nearest)
- [Google geocoding policies](https://developers.google.com/maps/documentation/geocoding/policies)
- [Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL)
- [OpenStreetMap copyright and licence](https://www.openstreetmap.org/copyright)

## Field capture latency and data integrity

A successfully validated GPS point is saved synchronously into browser local
storage and the capture button is immediately released. MongoDB writes run in a
single asynchronous, revision-ordered queue; a new bay replaces the pending
snapshot with the newest complete segment revision without cancelling an
in-flight request. Only the exact acknowledged snapshot is removed. Offline or
failed writes retain the latest snapshot for retry on reconnect/reload or during
the next operator action. This queue deliberately does **not** create a
background location watcher or transmit new coordinates without a capture.

**Finish & clear** still waits for MongoDB acknowledgement before discarding the
current segment, so a completed segment cannot be lost when the operator moves
on. Undoing the last bay syncs an empty revision to avoid leaving removed bays
in MongoDB. Browser local storage must not be manually cleared while a snapshot
is unsynchronised; JSON export remains available as an independent backup.

GPS capture now accepts two distinct fresh, qualifying fixes after 1.5 seconds,
or one fresh fix that meets the unchanged selected accuracy after a short
2.7-second settling period. It retains the best observed accurate fix and
terminates after 16 seconds if the device cannot meet the threshold. Device GPS
quality, permissions, and sky conditions still determine real capture time;
the application cannot guarantee a high-accuracy fix within a fixed deadline.

Street lookup retains the suburb/postcode validation and per-coordinate road
geometry resolver. A small ten-minute in-memory geometry cache speeds nearby
repeat lookups without caching chosen street names or intersections; unhealthy
OSM endpoints are temporarily skipped after failure. The first uncached lookup
still depends on the external Overpass provider. Predictable sub-second
intersection suggestions would require a provisioned, locally indexed
OpenStreetMap road-graph service rather than an unreliable public API.

## GPS quality

Each capture requests uncached high-accuracy browser geolocation updates for up to 16 seconds. It discards stale or invalid readings, requires multiple fresh fixes before accepting early, and retains the fix with the best device-reported accuracy. A point is **not saved** unless it meets the selected accuracy requirement (±5 m by default). The handset's precise-location setting, GPS hardware, surroundings, and satellite visibility still determine the accuracy available; use the application outdoors with a clear view of the sky.

The reported accuracy, number of fresh samples, sampling duration, and required accuracy are included with each exported point. Captures are retained locally immediately and autosaved to MongoDB when configured; JSON export remains available offline.

## Parking identifiers

**Parking area number**, **EasyPark / PayStay number**, and **Permit Number** are
all optional for numbered and unnumbered parking. For timed-only or unrestricted
parking without identifiers, leave all three blank rather than entering a
fabricated value. When provided, parking area and permit numbers accept text
(including letters, digits and hyphens), preserve leading zeroes, and are
trimmed at export. Street metadata and, for numbered bays, the starting bay
remain required.

The EasyPark and PayStay switches are mutually exclusive. Both may be off for
areas without either provider. An inactive payment input is retained as a local
draft but is not exported or counted as an identifier. Select a provider to edit
and include its number. An empty payment input is optional and does not activate payment.
Active payment numbers must be numeric; an existing EP-/PS- prefix
is accepted and replaced with the selected provider's prefix exactly once.

Examples:

| Input | JSON |
| --- | --- |
| All identifiers blank, both providers off | All identifiers `null`, `paymentRequired: false` |
| Parking area `MCC-TA`, both providers off | `parkingAreaNumber: "MCC-TA"` |
| Permit `MCC-TA01`, both providers off | `permitNumber: "MCC-TA01"` |
| EasyPark selected, number `7093` | `paymentAreaNumber: "EP-7093"`, `easyParkNumber: "EP-7093"` |
| PayStay selected, number `7093` | `paymentAreaNumber: "PS-7093"`, `payStayNumber: "PS-7093"` |

New exports use `civicmaps.parking_segment.v3`. The segment includes
`paymentProvider` (`EasyPark`, `PayStay`, or null), `paymentAreaNumber`,
`permitNumber`, `easyParkNumber`, and `payStayNumber`; unused values are null.
`paymentRequired` reflects an active provider number, independently of bay
numbering. This form models EasyPark/PayStay payment, not other payment methods.
Downstream consumers must support v3 and prefixed payment identifiers.
The permit input is a segment identifier; this change does not generate or
renumber individual bay allocations.

The server continues accepting legacy v2 payloads unchanged. Existing database
records and bay coordinates are not migrated. On restoring a legacy form with
an unprefixed payment number, the user must select its provider or explicitly
confirm neither provider before capture, save or export. No provider is guessed
from the old shared `easyParkNumber` field. The local form and points are retained.
New numbered and unnumbered segments do not require any identifiers. JSON export
uses `NO-IDENTIFIER` in the filename when all identifiers are absent.

For Talbot Street, enter `MCC-TA` as the parking area number and leave both
providers off; the previous placeholder `02` is not needed. Existing recorded
bay numbers require a separate correction and are not automatically changed.

## Run and verify

```sh
pip install -r requirements.txt
python server.py
```

Configure `MONGODB_URI` for database saves. Without it, captures remain local and
JSON export works. Open `http://localhost:8080` locally; use HTTPS on a handset.

```sh
node --test tests/*.test.cjs
python -m unittest discover -s tests -v
```

The service-worker shell cache is versioned for this update. The updated worker activates automatically; reload the app after deployment to load the new interface. Local capture data
is retained across this update.


### Suburb and postcode

Optional editable suburb and four-digit Australian postcode fields are saved in
local form state, JSON exports and MongoDB as `segment.suburb` and
`segment.postcode` (strings or null). Older records may omit both fields.
They are retained when starting the next segment to reduce repeated entry.

Auto-fill checks these hints against OpenStreetMap areas enclosing the fresh GPS
fix before resolving the on-street road and its connected boundaries. A known
locality mismatch stops auto-fill. If the map lacks a locality value, lookup
continues using GPS with a concise warning. Hints do not substitute for GPS or
select a block within a suburb. Manual entries remain editable and are preserved;
changing locality clears only untouched automatic street/boundary suggestions
before capture and discards any pending lookup response.

Provider recovery: both Overpass requests use HTTPS GET with a 12-second socket timeout per attempt. Socket timeouts are not an end-to-end deadline. A failed primary is skipped for 120 seconds when the fallback works; if both fail, retry is allowed after 10 seconds without repeated retries extending that pause. Locality validation and road topology resolution are unchanged.

### Expanding offline municipal coverage

`local-road-data.js` is the recovered 146-segment historical Melbourne CBD seed.
`municipal-road-pack.js` contains **one audited Footscray pilot block**: TALBOT STREET between COWPER STREET and a verified DEAD END (reviewed 15 October 2026). All remaining Footscray/Maribyrnong roads are unapproved; see `docs/maribyrnong-vicmap-review-20261015.md`.
Do **not** label Footscray, Maribyrnong or another municipality as covered until
real geometric road segments with audited between-street boundaries have been
packaged, regression-tested, and validated in field use.

`scripts/build_municipal_road_pack.py` converts independently reviewed WGS84
GeoJSON into a self-contained browser index pack. Each LineString feature must
carry: `roadSegmentId`, `street`, `from`, `to`,
`boundaryEndpointsVerified: true`, and preferably `suburb(s)` and `postcode`.
`from` and `to` identify actual bounding intersections or a verified dead end,
not arbitrary OSM way splits or nearest names. Missing topology causes rejection.
Two-point axes and multi-point curves are supported. Diagonal roads without
verified compass-side metadata intentionally leave side blank.

```bash
python scripts/build_municipal_road_pack.py \\
  --input reviewed-maribyrnong-segments.geojson \\
  --output municipal-road-pack.js \\
  --jurisdiction maribyrnong \\
  --source "Audited road geometry source" \\
  --licence "Verified dataset licence" \\
  --source-url "https://verified-data-source.example"
```

The source URL and licence **must** be replaced with the real source values.
The generated JS is loaded after the historical seed and before the matcher.
Bump the service worker cache version when replacing the pack so field devices
download the new audited dataset. Preserve raw source files, provenance, source
version, licence and audit outputs separately. Validate postcode/suburb matching,
parallel streets, road curves, junctions, dead ends, offline mode and side labels
on field devices before enabling municipality-wide claims.

Current locally indexed coverage is limited to the historical CBD seed plus the
reviewed Talbot Street Footscray pilot; the July CivicMAPS index declares 3,974 source City of Melbourne road
segments, but its imported suburb/type data and operational GPS coverage remain
unverified. The large historical `LOCAL_STREET_BLOCKS` table alone does not
contain complete GPS axes and must not be used to invent them.
