# GeoCapture

Mobile parking-bay location capture with a strict, operator-selectable GPS quality gate.

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
