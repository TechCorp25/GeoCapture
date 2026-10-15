# GeoCapture Phase 4 — City of Maribyrnong municipality-wide source inventory

**Audit date:** 15 October 2026 (UTC)  
**Repository:** TechCorp25/GeoCapture  
**Governance:** Empirical `CivicMAPS-rebuild` only; other CivicMAPS/PinForce repositories are excluded.  
**State:** Municipality acquisition, source completeness reconciliation, independent candidate audit and **unpublished** review-package staging completed. **Full operational road coverage and mobile field QA are NOT completed.**

## Original source preservation and provenance

Phase 3 original source artifacts were recovered without altering them:

- Original Footscray source: Actions artifact `11946024241`, zip SHA256 `0df95dc5d80e81ac6db3960f5addc75d9003e2ce2b93c830f78d32157903a94f`, raw road SHA256 `260d28ebcaadea2a5681c85c4245665ee44b8b0d3b1caa91c4bba99887728649`.
- Original Phase 3 audit: artifact `11947881909`, zip SHA256 `0732a09a65715181dbfc59d3e3ba178bb6df157766b1b37ccdaae5a32992dab2`, official LGA SHA256 `d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb`.
- Phase 4 source acquisition: `scripts/fetch_vicmap_roads.py --boundary ... --boundary-manifest ... --buffer-metres 600` using official LGA polygon and ArcGIS Transport TR_ROAD, source road SHA256 `3f5a4ee47b7e86cff22df5e82efde6afa866eacf42f07ad8b87fce2a944412bb`.
- Source provider attribution: **State of Victoria**, **CC BY 4.0**. No individual parking-bay or operator GPS records were copied into these source/review packs.

Phase 4 road acquisition envelope WGS84: `[144.83232328049982, -37.8323474585149, 144.92335033374718, -37.75040609666159]`. This is derived from the official council polygon with a 600-metre network buffer; **the envelope does not redefine the legal municipality**. ArcGIS returned exactly 10,097 object IDs before and after the paged snapshot, matching all 10,097 retrieved unique road features (PFI and object-ID duplicates rejected). Snapshot checksum is recorded independently of the earlier Footscray-only source.

## Independently reconciled inventory

| Unit | Audited total |
|---|---:|
| Official TR_ROAD features, buffered acquisition extent | 10,097 |
| Source features wholly inside council | 5,321 |
| Source features crossing/touching boundary | 107 |
| Source features outside council, retained only for junction context | 4,669 |
| Road-block candidates built from original network UFI/PFI graph | 4,148 |
| Independently source/topology qualified candidate blocks | 1,487 |
| Candidate blocks wholly outside municipality | 2,254 |
| Candidate blocks still pending explicit review | 407 |
| Previously published City of Maribyrnong PFIs | 33 |
| Previously published PFIs with exact (or reverse-axis equivalent) current geometry | 33 |
| Source road features requiring review (inside or crossing) | 4,160 |
| Source features in unsupported category inside LGA | 1,235 |

**Denominator warning:** Road *features* and identifiable *road blocks* are different units. Feature-class review remains open for 4,160 records; 1,487 source-qualified blocks do not mean 1,487 fully field-qualified blocks. The existing 33 published municipal road blocks are **retained**, with 146 historic Melbourne CBD blocks unchanged.

Candidate source-audit first-failure categories comprise 1,707 outside/crossing the LGA, 84 short, 264 near source-envelope margin, 7 conflicting junction names, 461 classification/access, 136 structures, and 2 unnamed connections. Subsequent polygon intersection classification separated 2,254 entirely outside candidates from 407 genuinely remaining to review (plus the 1,487 source-qualified candidates). Source-name, topology and field confidence gates remain separate from publication.

## Non-published locality staging

`scripts/stage_municipal_packs.py` compiled independently source-qualified candidates into **1,454 staged new blocks** distributed over ten GeoJSON locality/shared-junction review packs. It preserved a unique road-block ID, official geometry, original PFI, both bounding street names, source provenance and explicit `STAGED_OFFLINE_NOT_PUBLISHED` status. The exception manifest documents **32 previously published candidates** excluded to avoid duplication, and **one candidate crossing municipal boundary** withheld from staging. The previously published dead-end pilot does not reappear in these candidate-derived staged packages.

| Package | Source-qualified new blocks staged |
|---|---:|
| Footscray | 199 |
| West Footscray | 146 |
| Seddon | 107 |
| Yarraville | 284 |
| Kingsville | 29 |
| Maidstone | 168 |
| Maribyrnong | 233 |
| Braybrook | 195 |
| Tottenham | 6 |
| Shared localities / boundary | 87 |
| **Total** | **1,454** |

A stage package is **not** an approved GeoCapture production pack. Individual source/parity review and appropriate geographic/manual confidence gates must occur before release. Nothing in these scripts writes parking-bay records, overwrites production road data, or bypasses user-editable street and side fields.

## Reproduction and release gates

The `phase4-municipal-inventory.yml` GitHub Actions workflow executes:

1. Existing Python and JavaScript regressions.
2. Official Maribyrnong council polygon acquisition and SHA256 manifest.
3. Buffered polygon-based source collection with double object-ID reconciliation.
4. Network candidate generation using stable official PFI identities.
5. Independent UFI/geometry/classification/council audit and an explicit disposition ledger.
6. Source feature-level reconciliation with original 33 published PFIs.
7. Locality-based staging without duplicate or cross-boundary publication.
8. Artifact-level SHA256 manifest preservation and retained official GeoJSON + audit + package artifacts.

Original evidence is not overwritten. The generated artifact expires after its workflow's GitHub Actions retention window and must be preserved/exported separately when required.

**Remaining Phase 4 work:** independently resolve 407 pending candidate blocks and the relevant 4,160 pending source-feature cases; investigate 1,235 unsupported features (including genuinely unsupported roads and unnamed accesses); separately validate dead ends, unusual junctions, roundabouts, structures, short blocks and locality-boundary roads; approve subsets for production release with source evidence; implement efficient automatic GPS-driven package discovery/selection for reviewed packs; run device GPS/side-of-road and repeated parking-bay MongoDB sync field tests; publish only independently verified blocks; finally reconcile `main` against the LIVE Render commit. A complete municipality-wide production coverage claim is not yet justified.
