# GeoCapture — Maribyrnong Vicmap review and pilot

**Review date:** 15 October 2026  
**Repository:** TechCorp25/GeoCapture  
**Scope:** bounded Footscray study area and reviewed Talbot Street pilot  
**Status:** One road block approved for local offline lookup; wider data are unapproved candidates

## Authoritative road geometry

- Dataset: Vicmap Transport — TR_ROAD (State of Victoria, Department of Transport and Planning)
- Dataset: https://discover.data.vic.gov.au/en_AU/dataset/vicmap-transport-road-line
- Service: https://vicmap.land.vic.gov.au/agsgis/rest/services/vicmap/Vicmap_Transport/MapServer/1
- License: CC BY 4.0, attribution retained on exported segment metadata
- Study-area WGS84 bbox: [144.87, -37.835, 144.945, -37.785]
- Acquisition: 2026-10-15 03:37:19 UTC
- Data checksum (SHA-256 of GeoJSON): `260d28ebcaadea2a5681c85c4245665ee44b8b0d3b1caa91c4bba99887728649`
- Count: 6,466 official road features in bbox; bounded area is NOT City of Maribyrnong's legal boundary
- Topology review: 6,327 eligible road edges; **1,995 unapproved candidate named-intersection street blocks**; rejected 139 structured features
- Additional ambiguity cases observed: unnamed junction, multiple named roads, branch, possible terminus, bbox boundary; none eligible for automatic promotion without review
- GitHub Actions source-acquisition run: https://github.com/TechCorp25/GeoCapture/actions/runs/38677177208
- The original raw source, source manifest, candidate GeoJSON and topology-audit report are retained in that workflow artifact; not committed to the production bundle.

## Reviewed pilot: Talbot Street, Footscray

- Official feature: TR_ROAD PFI `5669272`, one LineString between network junction nodes
- Cowper Street junction: Vicmap node `2306500`, connected to COWPER STREET
- Road terminus: Vicmap node `18845605`, degree 1 in returned road network
- Start WGS84: [longitude 144.9039780490001, latitude -37.80225195908597]
- End WGS84: [longitude 144.90275580500008, latitude -37.80188509308594]
- Independent field metadata check: previously captured GeoCapture TALBOT STREET, FOOTSCRAY 3011, between DEAD END and COWPER STREET, SOUTH side, seven recorded bays. Raw bay point coordinates, timestamps, and user evidence records are NOT copied to the public GeoJSON or local JS data pack.
- QA outcome: street name, two boundaries, terminal node and road geometry agree. For this road axis the GPS sample offsets are consistently on the side assigned SOUTH; uncertain fixes still produce no automatic side.
- Local data pack: `municipal-road-pack.js`, 1 reviewed block appended to the 146 historic Melbourne CBD segments.
- Audited input: `data/reviewed/maribyrnong-talbot-cowper-dead-end.geojson`
- Known bound: this pilot is *not* evidence that all of Footscray, Maribyrnong or the entire 1,995 candidate set is ready.

## Engineering controls

1. Only verified street name/boundary pairs with official geometry can be published to `municipal-road-pack.js`.
2. `scripts/fetch_vicmap_roads.py` acquires bounded official data at build time. The mobile application does not contact Vicmap.
3. `scripts/review_vicmap_topology.py` emits `boundaryEndpointsVerified: false` for all review candidates; the production pack builder deliberately rejects them until independently checked.
4. `scripts/build_municipal_road_pack.py` is the validated GeoJSON-to-browser-pack compiler. Preserve review evidence and dataset licence.
5. Source pack version changes require updating `sw.js` cache version, unit tests, and Render deployment confirmation.
6. Side-of-street uncertainty, near-intersection ambiguity, manual overrides, and remote fallback still apply unchanged.
7. No new paid API or end-user road-lookup request is required for the reviewed pilot.

## Outstanding acceptance

- Validate the remaining Footscray candidate list against independent intersection information and field observations; do not bulk approve based on a matching street name alone.
- Acquire entire council boundary polygon and distinguish genuine municipal coverage from the current rectangle.
- Investigate road termini, bridges, names repeated on nearby carriageways, curves and places with multiple cross-streets.
- Measure on-device GPS acquisition plus local lookup latency and confirm offline operation in the installed PWA.
- Assess field operator handling where side remains blank because GPS accuracy cannot distinguish carriageway side.
- Document versioned refresh procedures and review before enabling more municipal packs.
