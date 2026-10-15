# GeoCapture Phase 3 — independently audited municipal network

**Date:** 15 October 2026
**Governance:** CivicMAPS-rebuild / TechCorp25/GeoCapture; unrelated CivicMAPS/PinForce data is out of scope.
**Status:** Phase 3 audit tooling, NOT an approved expansion of the production data pack.

## Source and legal council boundary

Road geometry: Vicmap Transport TR_ROAD (State of Victoria, CC BY 4.0), sourced by
`scripts/fetch_vicmap_roads.py`. Historical 15 October source
SHA-256: `260d28ebcaadea2a5681c85c4245665ee44b8b0d3b1caa91c4bba99887728649`.

The original archive is GitHub Actions artifact `11946024241`, workflow
`38677177208`, expiring 14 November 2026 UTC. It includes source GeoJSON,
manifest, 1,995 candidate blocks and topology audit. Preserve and checksum
the original; a fresh snapshot must have its own retrieval date and checksum.

Authoritative LGA: **Vicmap Admin LGA_POLYGON, layer 9** (property-aligned),
https://vicmap.land.vic.gov.au/agsgis/rest/services/vicmap/Vicmap_Admin/MapServer/9.
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
