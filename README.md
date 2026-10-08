# GeoCapture

Mobile parking-bay location capture with a strict, operator-selectable GPS quality gate.

## Street and boundary auto-fill

After an operator enables lookup, tap **Auto-fill street & between streets** before capturing the first bay. The
app takes a fresh fix using the existing GPS quality gate, finds the current
street, and follows its connected road geometry in both directions to suggest
the adjoining street or `DEAD END`. Review the result against the signs on site.
The lookup does not record a bay or replace any measured bay coordinates.

All three text fields remain editable. Only blank fields are filled. Existing
entries, including edits or deletions made while a request is running, are kept.
Clear an entry to request a new suggestion. Editing the street removes boundaries
previously auto-filled for that street; manual boundaries are retained for review.
Leaving the street field triggers another boundary lookup if the previous GPS fix
is less than 60 seconds old. Otherwise tap auto-fill to obtain a fresh fix.
Finish & clear now clears street, boundaries and side before the next segment.
Auto-fill is unavailable once a segment contains captured bays; its metadata can
still be corrected manually. This prevents a new location changing an active survey.

### Providers and configuration

The saved street/boundary names are derived independently from **OpenStreetMap**
road topology through Overpass. A Google reverse-geocoded street is optionally
shown as a separate, transient reference. Google does not expose both adjacent
intersections or a dead-end flag through its documented Geocoding / Roads APIs.
Google data never selects the OSM road, populates form fields, enters local form
storage, or enters exported JSON / MongoDB. Enabling Google adds a reference check,
not additional boundary coverage. No Google API key is needed for auto-fill.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `STREET_LOOKUP_ENABLED` | `false` | Set `true` after approving coordinate transfer to the configured road provider. Manual entry remains available when disabled. |
| `OVERPASS_API_URL` | `https://overpass-api.de/api/interpreter` | HTTPS Overpass endpoint, supplied by the operator only. |
| `GOOGLE_MAPS_API_KEY` | unset | Optional server-only Geocoding API key; enables the Google street reference. |

For Google, enable the Geocoding API in a billing-enabled Google Cloud project,
restrict the key to that API and the server's allowed outbound addresses, set
provider quotas, and configure it as a Render secret. Never put it in HTML or git.
Before enabling Google in production, provide the application Terms of Use and
Privacy Policy required by Google. Google results are displayed with attribution
without a map and are not cached or saved by this application.

The feature is disabled in the Render blueprint until the operator approves the
additional road-data provider. Local tests use synthetic road networks / provider
responses. A live Overpass check was blocked by automatic approval review because
only Google had been proposed by the user. No live provider verification or Google
API-key verification is claimed by this change.

Lookups send the requested coordinate to the configured road provider and, only
when its key is configured, Google. There is no background location watching,
peer sharing, or continuous upload. The GPS watcher closes when sampling finishes.
The lookup endpoint uses POST so coordinates are absent from request URLs, returns
`Cache-Control: no-store`, and is excluded from the service-worker cache. No lookup
coordinates or raw provider responses are saved by the backend. Upstream providers
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

## GPS quality

Each capture requests uncached high-accuracy browser geolocation updates for up to 30 seconds. It discards stale or invalid readings, requires multiple fresh fixes before accepting early, and retains the fix with the best device-reported accuracy. A point is **not saved** unless it meets the selected accuracy requirement (±5 m by default). The handset's precise-location setting, GPS hardware, surroundings, and satellite visibility still determine the accuracy available; use the application outdoors with a clear view of the sky.

The reported accuracy, number of fresh samples, sampling duration, and required accuracy are included with each exported point. Captures are retained locally immediately and autosaved to MongoDB when configured; JSON export remains available offline.

## Parking identifiers

Enter at least one of **Parking area number**, **EasyPark / PayStay number**, or
**Permit Number**. Parking area and permit identifiers accept text (including
letters, digits and hyphens), preserve leading zeroes, and are trimmed at export.
This rule applies to numbered and unnumbered parking. Street metadata and, for
numbered parking, the starting bay remain required.

The EasyPark and PayStay switches are mutually exclusive. Both may be off for
areas without either provider. An inactive payment input is retained as a local
draft but is not exported or counted as an identifier. Select a provider to edit
and include its number. An empty payment input is optional if another identifier
is present. Active payment numbers must be numeric; an existing EP-/PS- prefix
is accepted and replaced with the selected provider's prefix exactly once.

Examples:

| Input | JSON |
| --- | --- |
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
Unnumbered legacy segments without identifiers need one entered before saving.

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
