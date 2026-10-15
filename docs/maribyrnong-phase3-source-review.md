# GeoCapture Phase 3 — independently audited municipal network

**Date:** 15 October 2026
**Governance:** CivicMAPS-rebuild / TechCorp25/GeoCapture; unrelated CivicMAPS/PinForce data is out of scope.
**Status:** Phase 3 official-source validated Footscray expansion: 32 additional road blocks in separate offline browser pack. Physical-handset validation still outstanding.

## Source and legal council boundary

Road geometry: Vicmap Transport TR_ROAD (State of Victoria, CC BY 4.0), sourced by
`scripts/fetch_vicmap_roads.py`. Historical 15 October source
SHA-256: `260d28ebcaadea2a5681c85c4245665ee44b8b0d3b1caa91c4bba99887728649`.

The original archive is GitHub Actions artifact `11946024241`, workflow
`38677177208`, expiring 14 November 2026 UTC. Successful official polygon and
candidate audit: workflow 38680317718, evidence artifact 11947614760, 14 November expiry. It includes source GeoJSON,
manifest, 1,995 candidate blocks and topology audit. Preserve and checksum
the original; a fresh snapshot must have its own retrieval date and checksum.

Authoritative LGA: **Vicmap Admin LGA_POLYGON, layer 9** (property-aligned),
https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/Vicmap_Admin/FeatureServer/9.
Acquired 2026-10-15T04:13:43Z; SHA-256: d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb. Feature LGA name MARIBYRNONG, PFI 341.
Also State of Victoria, CC BY 4.0. `scripts/fetch_vicmap_lga.py`
fails closed unless precisely one feature named MARIBYRNONG with polygonal
geometry is returned. The original Footscray bounding rectangle is **not**
the legal council boundary. Road features must be acquired with an outward
buffer so junctions near the council edge are not silently trimmed.

## Reproducible independent audit

`scripts/audit_municipal_candidates.py`:
- Verifies the raw road-snapshot checksum against the acquisition manifest.
- Reconstructs each review candidate's coordinates exclusively from the
  referenced original PFI edges, requiring UFI network continuity.
- Requires a single verified *other* named road at each terminal source node.
- Rejects grade separation and non-road structures, unnamed junctions,
  non-operational roads, unsupported classes/access, inconsistent geometry,
  very short road blocks and incomplete connections.
- Requires official LGA geometry (and its SHA-256 manifest), and both terminal
  endpoints plus midpoint to be inside the municipality.
- Does **not** infer postcode or cardinal side from noisy GPS or street name.
- Produces a disposition for each candidate, staged eligible GeoJSON, and a
  report counting eligible, pending and rejected candidates.
- Staged eligibility is NOT a production approval: publication remains
  separate, including verification of duplicates, priority surveys,
  geographic completeness and real-device GPS accuracy.

Run the `phase3-municipal-audit.yml` workflow on the Phase 3 feature
branch. Its retained artifact contains all source evidence, manifests,
dispositions, and staging GeoJSON. No artifact is automatically imported
into `municipal-road-pack.js`; unchanged production data remain intact.

## Recovered 15 October source pre-boundary audit

Using the exact recovered 6,466-feature source and 1,995-candidate snapshot:

| Candidate disposition (without official LGA loaded) | Count |
|---|---:|
| Pending LGA containment after source geometry checks | 1,466 |
| Pending short blocks (<12 m) | 85 |
| Pending source class/access review | 347 |
| Pending structures at intersections | 90 |
| Pending conflicting intersection name | 7 |
| Total pending | 1,995 |
| Independently eligible for publication before boundary acquisition | 0 |
| Rejected | 0 |

These reason categories are mutually exclusive first-failure results, **not**
a claim that all other conditions were checked or passed for each candidate.
They will change once official polygon containment is introduced. A later
Vicmap snapshot may also have different candidate numbers.

**Currently live:** one reviewed Talbot Street / Cowper Street–dead end
Footscray road block, plus 146 historical Melbourne CBD segments. Other
Footscray, Yarraville, Seddon, Kingsville, West Footscray and wider council
areas remain unconfirmed for offline road matching pending package release.

## Verified official council-polygon audit

The official polygon and complete TR_ROAD source were independently acquired, SHA256 verified and audited against 1,995 candidates.

| Disposition | Road blocks |
|---|---:|
| Eligible for separate packaging review | 826 |
| Pending outside/crossing LGA | 640 |
| Pending short blocks | 85 |
| Pending road class/access questions | 347 |
| Pending structures at junctions | 90 |
| Pending intersecting-name conflicts | 7 |
| Total | 1,995 |

The 826 are official-source topology qualified, not automatically release approved. The 1,169 pending remain blocked; status is first failure, not a claim all other checks passed.

## Approved source-verified Footscray pilot expansion

Exactly **32** independently audited Footscray local-road PFI segments were individually selected from the 826 after checking one original PFI each, connected named junctions at both UFI endpoints, operational class-5 road status, permitted vehicle access, explicit FOOTSCRAY locality, full official council polygon membership, unmodified two-point straight road axis, road length 45–220 m, and position within a 650 m study corridor centred on the Talbot pilot. No guessed dead ends or inferred postcodes were included.

- Permanent reviewed source: data/reviewed/maribyrnong-footscray-phase3-20261015.geojson
- Separately versioned browser source: municipal-road-phase3.js
- Existing Talbot Street and historic CBD files preserved unchanged.
- Offline PWA shell updated to cache version 14 and preload the Phase 3 pack.
- 146 historical CBD blocks + 1 verified Footscray Talbot block + 32 additional verified Footscray blocks = **179 locally indexed road blocks**.
- Provenance includes original road source SHA256 260d28ebcaadea2a5681c85c4245665ee44b8b0d3b1caa91c4bba99887728649 and official LGA SHA256 d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb.
- Every new block remains labelled official-topology-validated, handset-GPS QA pending. This release does NOT assert full Footscray or Maribyrnong municipality coverage.
- The remaining 794 official-network staged blocks were not published, alongside 1,169 pending disposition candidates.

The source verifier scripts/verify_phase3_footscray.py fails closed when any published geometry, PFI, boundary name, geographic membership or road/council SHA256 differs from the official independently audited snapshot. Newer downloaded government data must undergo separate source review rather than silently overriding this release.

Field acceptance outstanding: live smartphone GPS acquisition latency, side on actual carriageways, near-junction ambiguity, override persistence, PWA cache refresh/restart, out-of-coverage fallback, and MongoDB asynchronous retry. Node local matching performance is separately measured and is not a proxy for these end-to-end timings.

## Release gates

1. Inspect official LGA geometry, all candidate dispositions, geometry
   overlays and source PFI/UFI evidence; review parallel carriageways and
   roundabouts before approving a published subarea.
2. Limit initial packaging to independently audited Footscray blocks. Add
   field-priority evidence for previous GeoCapture survey streets.
3. Check duplicate road geometries, postal and suburb attribution, source
   versions and licensing. Do not change any historical parking-bay record.
4. Compile the staged, separately approved GeoJSON through
   `scripts/build_municipal_road_pack.py`; inspect output, update
   `municipal-road-pack.js` and `sw.js` cache version together.
5. Run all JavaScript/Python tests plus physical-handset tests for GPS fix
   acquisition, p95 matching, offline refresh, side uncertainty, override
   persistence and asynchronous MongoDB sync.
6. Merge only after passing release review, check Render main/live commit
   parity, and record precise outcomes in Empirical CivicMAPS-rebuild.
