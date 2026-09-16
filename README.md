# GeoCapture

Mobile parking-bay location capture with a strict, operator-selectable GPS quality gate.

## GPS quality

Each capture requests uncached high-accuracy browser geolocation updates for up to 30 seconds. It discards stale or invalid readings, waits for multiple fresh fixes, and retains the fix with the best device-reported accuracy. A point is **not saved** unless it meets the selected accuracy requirement (±5 m by default). The handset's precise-location setting, GPS hardware, surroundings, and satellite visibility still determine the accuracy available; use the application outdoors with a clear view of the sky.

The reported accuracy, number of fresh samples, sampling duration, and required accuracy are included with each exported point. All data remains in browser storage until the operator copies or exports it.
