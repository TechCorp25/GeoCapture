# CODEX INSTRUCTIONAL PROMPT — CivicMAPS GPS Capture Railway Deployment

## Mission

You are receiving a complete standalone application package named **CivicMAPS GPS Capture**.

Your task is to inspect it, preserve its intended field-capture behaviour, deploy it to **Railway**, verify the live deployment, and return the final public HTTPS URL plus a concise verification report.

This service is intended for the **CivicMAPS / EnforcementMaps on-street parking location data workflow**.

Do not redesign or substantially rewrite the application unless a defect prevents reliable deployment or GPS capture. Preserve the existing data model and field workflow unless a change is technically necessary.

---

## Operational purpose

The operator walks a street segment from parking bay to parking bay.

Before capture, the operator enters:

- current street segment name
- between street A
- between street B
- nautical/cardinal side of the street: NORTH / SOUTH / EAST / WEST
- parking area number
- EasyPark number
- starting bay number
- whether bay numbering is ascending or descending

At each physical parking bay, the operator presses one button.

The application must then request a fresh **high-accuracy device geolocation fix**, sample available GPS fixes for a short period, retain the most accurate fix returned, and record that fix against the next bay number.

The exported JSON is intended to feed CivicMAPS / EnforcementMaps location data.

Example operational sequence:

- Street: ELIZABETH STREET
- Between: LITTLE LONSDALE STREET and LONSDALE STREET
- Side: WEST
- Parking Area: 533
- EasyPark: 7391
- Starting Bay: 28
- Sequence: descending
- Captures: 28 → 27 → 26 → 25

---

## Source package

Read all files before changing anything, especially:

- `index.html`
- `server.py`
- `manifest.json`
- `sw.js`
- `railway.json`
- `Procfile`
- `README.md`

The application currently has no third-party runtime dependencies.

`server.py` uses Python's standard library and must bind to Railway's injected `$PORT`.

---

## Required deployment target

Deploy to **Railway**.

Preferred process:

1. Create or select an appropriate Railway project.
2. Create a service from this source package/repository.
3. Allow Railway/Nixpacks to detect Python.
4. Start the service with:

   `python server.py`

5. Ensure Railway injects and the app uses `$PORT`.
6. Confirm the health check succeeds at:

   `/health`

7. Generate or enable a public Railway domain.
8. Ensure the final public URL uses HTTPS.

Do not require a database.

Do not introduce a backend datastore unless explicitly necessary to fix a demonstrated defect.

---

## Functional requirements that must remain intact

### Segment metadata

The interface must retain fields for:

- street segment name
- between street A
- between street B
- side of street
- parking area number
- EasyPark number
- starting bay number
- ascending / descending bay sequence

### GPS capture

Each capture action must:

- use browser/device geolocation
- request `enableHighAccuracy: true`
- reject stale cached locations by using `maximumAge: 0`
- obtain a fresh location result
- collect live fixes for a short sampling interval
- retain the best reported accuracy received during that interval
- record:
  - bay number
  - latitude
  - longitude
  - reported accuracy in metres
  - timestamp
  - altitude when available
  - altitude accuracy when available
  - heading when available
  - speed when available

### Bay numbering

The application must automatically advance the bay number after each successful capture according to the chosen ascending/descending sequence.

### Persistence

The current segment form and captured points should remain available locally on the device using browser storage so an accidental refresh does not immediately destroy field work.

### Field controls

Preserve:

- capture next bay
- undo last capture
- clear current segment
- copy JSON
- export/download JSON

### PWA behaviour

Preserve:

- `manifest.json`
- service-worker registration
- offline-capable application shell after first successful load

Do not allow service-worker caching to prevent deployment updates from eventually reaching the operator.

---

## JSON contract

Preserve the existing general structure:

```json
{
  "schema": "civicmaps.parking_segment.v1",
  "segment": {
    "street": "ELIZABETH STREET",
    "between": [
      "LITTLE LONSDALE STREET",
      "LONSDALE STREET"
    ],
    "side": "WEST",
    "parkingAreaNumber": "533",
    "easyParkNumber": "7391"
  },
  "capture": {
    "source": "device_geolocation",
    "enableHighAccuracy": true,
    "generatedAt": "ISO-8601 timestamp",
    "pointCount": 4
  },
  "bays": [
    {
      "bay": 28,
      "latitude": -37.8117,
      "longitude": 144.9617,
      "accuracy": 3.8,
      "altitude": null,
      "altitudeAccuracy": null,
      "heading": null,
      "speed": null,
      "capturedAt": "ISO-8601 timestamp"
    }
  ]
}
```

Do not silently rename existing JSON keys or change schema semantics.

If you believe the schema needs extension, add fields in a backward-compatible way and document the reason.

---

## Accuracy requirement

Do not describe phone GPS as mathematically exact.

The application must preserve the device-reported `accuracy` value for every point.

The deployment should make it obvious to the field operator when a fix has poor reported accuracy.

A parking-bay dataset should not treat an address geocode or browser-derived street centroid as a substitute for the raw device geolocation reading.

---

## HTTPS requirement

Browser geolocation requires a secure context in normal production use.

Therefore the Railway deployment must expose the application through **HTTPS** before GPS testing is considered complete.

---

## Verification requirements

After deployment, verify all of the following.

### Server/deployment

- public Railway service is running
- `/` returns the application
- `/health` returns HTTP 200 and JSON status `ok`
- HTTPS works
- no obvious server-side errors

### Frontend

Confirm the page contains and renders:

- street segment field
- two between-street fields
- side-of-street selector
- parking area field
- EasyPark field
- starting bay field
- sequence selector
- Capture next bay button
- captured bays table
- Undo last
- Clear current segment
- Copy JSON
- Export JSON

### Browser logic

Inspect the deployed JavaScript and confirm:

- `navigator.geolocation` is used
- `enableHighAccuracy: true`
- `maximumAge: 0`
- fresh fixes are sampled
- best accuracy is selected
- captures increment/decrement bay number correctly
- JSON export contains segment metadata and bay coordinates
- localStorage persistence remains functional

### Mobile geolocation limitation

If your execution environment cannot provide genuine phone GPS coordinates, do **not** fabricate a GPS test.

Instead:

1. verify the browser geolocation code path structurally,
2. confirm HTTPS is live,
3. report that final physical GPS validation must be completed on the operator's Android handset,
4. provide the deployed URL for that test.

---

## Defect handling

You are authorised to fix:

- Railway build/start failures
- incorrect port binding
- health-check issues
- broken PWA/service-worker behaviour
- malformed JSON export
- JavaScript runtime errors
- mobile rendering problems
- bugs preventing geolocation
- bugs causing duplicate/stale capture values
- persistence defects

Avoid scope expansion.

Do not add authentication, accounts, databases, maps, analytics, telemetry, or third-party tracking unless explicitly requested.

Do not send captured locations to a remote server. The present design is local-device capture with JSON export.

---

## Privacy constraint

The captured coordinates are operational municipal parking-location data.

The application must not transmit captured GPS points to third parties as part of normal capture.

Do not add analytics or tracking SDKs.

Do not introduce any external API that receives the coordinate data.

---

## Expected completion report

Return:

1. Railway project/service name
2. public HTTPS URL
3. `/health` verification result
4. deployment status
5. any source changes made
6. whether browser-level functional checks passed
7. whether true mobile GPS validation was performed or remains for the handset
8. any material limitations discovered

If deployment cannot be completed because Railway authentication or account authorisation is unavailable, stop at that boundary and state the exact action the user must take. Do not substitute another hosting provider unless instructed.

---

## Definition of done

The task is complete when:

- the package deploys successfully on Railway,
- a public HTTPS URL is available,
- `/health` is healthy,
- the field-capture UI loads correctly,
- the geolocation implementation is preserved and structurally verified,
- JSON export remains valid,
- and any remaining handset-only GPS validation is clearly identified.

