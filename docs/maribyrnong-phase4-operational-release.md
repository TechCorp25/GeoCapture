# GeoCapture Phase 4 — municipal network operational expansion and remaining field gates

**Date:** 15 October 2026.  
**Owner/workspace:** CivicMAPS-rebuild; TechCorp25/GeoCapture exclusively.  
**Release state:** Source-topology validated municipal road blocks ready for local handset lookup; full municipality coverage NOT certified. Existing captured MongoDB road segments and field corrections are unchanged.

## Published source-qualified inventory

Phase 4 began with the exact retained official Vicmap snapshot and council polygon rather than importing geodata from other projects.

| Status | Road blocks |
|---|---:|
| Existing source-verified Maribyrnong road blocks, preserved (Phase 2–3) | 33 |
| Newly independently audited and published for local lookup | 1,635 |
| **Total source-verified Maribyrnong road blocks** | **1,668** |
| Municipality-wide named intersection candidates | 4,148 |
| Whole-council candidates confirmed outside the polygon | 2,254 |
| Candidate blocks awaiting further source/physical verification | 226 |
| Additional potential physical road terminals awaiting field confirmation | 318 |
| Existing separately field-verified dead end retained | 1 |

The 1,635 new blocks contain **2,405** segmented road-geometry edges. Together with 146 historical Melbourne CBD + 33 existing Maribyrnong edges, the complete installed GeoCapture bundle can index **2,584 geometry edges**. This edge count is NOT a municipality completeness denominator.

The source review explicitly includes officially defined Vicmap class 2 arterial and class 6 minor-access roads, in addition to classes 3, 4 and 5. Eligibility continues to demand class-appropriate source road status `O`, vehicle access `1`, feature type ROAD, no named structure, independently reconstructed PFI geometry and a single named intersecting road at both terminal UFIs. No highway/freeway/trail, unopened road, bridge-structure ambiguity, unnamed junction, unsupported edge or presumed dead end was automatically published.

- Road TR_ROAD SHA256: `3f5a4ee47b7e86cff22df5e82efde6afa866eacf42f07ad8b87fce2a944412bb`
- Official council polygon SHA256: `d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb`
- Official attribution: State of Victoria, CC BY 4.0.
- Class reference: https://www.localgovernment.vic.gov.au/__data/assets/pdf_file/0011/210026/Vicmap-Transport-Road-Classification.pdf

## Locally installed packages

`municipal-data/manifest.json` authorizes ten locality/shared-boundary packages for GPS-based loading, retains SHA256 per package and explicitly declares `operationalCoverageComplete: false`. `municipal-road-loader.js` checks source SHA, council SHA, package version, package checksum and segment review states, then adds only relevant segments to the existing local spatial matcher. Geometry for other localities is not unnecessarily loaded into memory. Service worker v16 pre-caches the small whole-council package set to support installed offline PWA use.

| Logical pack | New blocks |
|---|---:|
| Braybrook | 207 |
| Footscray | 224 |
| Kingsville | 31 |
| Maidstone | 196 |
| Maribyrnong | 248 |
| Seddon | 107 |
| Shared localities | 113 |
| Tottenham | 9 |
| West Footscray | 170 |
| Yarraville | 330 |
| **Total** | **1,635** |

Captured parking-segment v3 exports now retain `roadNetworkSegmentId` (the stable matched geometry-edge identity) and `roadNetworkBlockId` (the official PFI-based road-block identity), alongside `roadMatch` provenance containing source review status, GPS accuracy and lateral match distance. These identifiers are recorded **only when the fields still agree with the local source match**; manually changing the street, locality or between-street boundaries invalidates the stored match identity. Editing the cardinal side does not overwrite or fabricate source topology. Existing historical records remain valid and unmodified. These fields are operator metadata, not a substitute for independent municipal source verification.

For official arterial class-2 road features the cardinal side is deliberately **unset** until actual-device/field verification. The existing GPS uncertainty/centreline ambiguity gates remain effective for other road classes. Postcodes are not inferred. All automatic fields remain editable, with operator overrides preserved.

## Complete field-review queue for source terminals

`scripts/audit_municipal_terminals.py` separately inventories degree-one UFI nodes within the official municipality. The complete buffered source graph is used; road status, access, structure and council membership are checked. Its immutable audit artifact contains the exact source PFIs, terminal UFI, coordinates, street name and locality for each case.

There are **319 terminal-source candidates**: one previously field-verified TALBOT STREET dead-end reference and **318 additional source candidates requiring independent physical terminal confirmation**. A degree-one UFI does not independently prove the road is a real physical dead end, and an isolated official line never becomes a verified junction by itself.

Field-reviewers should record (a) exact UFI/PFI; (b) true physical terminal or through access; (c) the independently confirmed nearest named intersecting street; (d) whether any bridge, private connection, access lane or pedestrian continuation explains the endpoint; (e) dated evidence; and (f) reviewer identity/acceptance. Publish a verified dead end only after this evidence is accepted. Manual override is always available meanwhile.

## Remaining candidate dispositions

The 226 pending intersection block candidates comprise short blocks, boundary-crossing roads, road status/class/access questions, unsupported structures and multiple-name junction ambiguity. Maintain explicit `PENDING_REVIEW` or `AMBIGUOUS` status until individually resolved; do not promote them to source-verified based on nearest-coordinate geometry or lack of an alternative.

Any source features that are not represented by the published set must remain in the source-feature ledger as `PENDING_REVIEW`, `UNSUPPORTED`, `OUT_OF_SCOPE` or another documented disposition. Reuse the original 10,097-feature snapshot and audits for that reconciliation. This pipeline does not certify every named street in the council as matchable.

## Performance and production release evidence

- Full CI: 59 Node tests passed, Python regression tests passed, no failed step.
- Node-only local matcher p95: **0.034 ms** for the **2,584-edge** loaded local data bundle, excluding GPS receiver, network, PWA lifecycle and MongoDB sync.
- Source-specific publication audit independently checked each additional eligible candidate's UFI/PFI topology, original geometry, official council membership, duplicate PFI restrictions, class/access and provenance. Corrupted or mismatched packages are rejected by the runtime.
- Stale manual edits and outstanding captured parking bays continue to take precedence over any background result.
- Remote provider remains exception-only for unverified/uncovered GPS locations.

**Do not certify Phase 4 as complete until physical handset QA is performed:** side-of-street on real curving/parallel roads; junction ambiguity; terminal verification; offline SW install/update; measured GPS time-to-fix; repeated parking-bay capture cycle p50/p95; MongoDB retries and no cross-segment data loss; and correct package changes around municipality and suburb boundaries.

The released 1,635 additions are usable source-topology-qualified data. They are NOT a guarantee of universally accurate field results or completely surveyed roads.

## Preserved evidence and reproducibility

GitHub Actions release workflow `phase4-publish-reviewed.yml`, successful expanded official source and terminal audit: https://github.com/TechCorp25/GeoCapture/actions/runs/38691132850. The associated retained artifact contains static pack bytes and manifest, fresh candidate audit results, 319 terminal review entries and report. Historical Phase 3 + Phase 4 source ZIPs remain preserved in the ChatGPT Library at `/CivicMAPS-rebuild/GeoCapture/Maribyrnong/source-evidence/`. Refresh expired GitHub artifacts from those immutable snapshots; never assume a new acquisition has an identical checksum.
