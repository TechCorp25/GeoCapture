# GeoCapture Phase 4 — 15 October 2026 targeted geographic reconciliation pass 2

**Project:** GeoCapture / CivicMAPS-rebuild only. **Scope:** original 203 pending road blocks, without field testing, unrelated source-feature adjudication or terminal review. **Status:** partial non-field source reconciliation; operational municipal coverage remains uncertified.

## Verified additions to the existing ten-package street matcher

Six candidate IDs previously flagged `source_intersection_not_unique` are now source-qualified for the Yarraville package:

| Candidate ID | Surface street | Named bounding junctions |
| --- | --- | --- |
| `vicmap-5677562` | Hyde Street | Lennox Street — Schild Street |
| `vicmap-20230918-20230919` | Newcastle Street | Ballarat Street — Stephen Street |
| `vicmap-5679335` | Norfolk Street | Ballarat Street — Stephen Street |
| `vicmap-5677563` | Schild Street | Ducker Street — Hyde Street |
| `vicmap-5679529` | Stephen Street | Newcastle Street — Norfolk Street |
| `vicmap-5679766` | Stephen Street | Francis Street — Newcastle Street |

**Primary evidence:** `docs/phase4-six-atgrade-tunnel-reviews-20261015.json`, original preserved `GeoCapture_Phase4_Audit_and_Field_Review_20261015.zip`, official Vicmap TR_ROAD snapshot SHA-256 `3f5a4ee47b7e86cff22df5e82efde6afa866eacf42f07ad8b87fce2a944412bb` and Maribyrnong LGA polygon SHA-256 `d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb`.

On each candidate, the source UFI network includes West Gate Tunnel Tollway `feature_type_code=tunnel`, `class_code=0` features at one or both road junctions. The named surface-road neighbors remain distinct and correctly identified when underground connections are excluded from at-grade intersection enumeration. Each candidate's official surface PFI geometry is fully within the source LGA polygon, access 1, open status O, class 3–5, and no candidate PFI was already published. **No physical-device or construction-state field verification is claimed.**

The six new road blocks supply nine geometry edges. **Only Yarraville receives new edges**, but all ten package files have been re-versioned to `maribyrnong-phase4-20261015-v3` to avoid partial cache/version drift. Manifest SHA-256, loader pin and service worker cache v19 are coordinated. Prior package geometries, source PFIs and operator edits remain unchanged; unknown postcodes stay empty, and the GPS uncertainty rules remain in force.

## Original block denominator reconciled

| Disposition | Count |
| --- | ---: |
| Source-qualified, published blocks (baseline 1,668 + 6) | 1,674 |
| Out of municipal scope | 2,254 |
| Source-verified unsupported (23 class-9 trails + 8 class-0 freeway/ramp) | 31 |
| Still requiring independent non-field source investigation | 189 |
| **Original candidate total** | **4,148** |

From the original 226 pending IDs: 23 historic trail exclusions + 8 additional freeway exclusions + 6 new publications + 189 remaining source investigations = 226. These are source-only adjudications; no new field-only cases have been asserted.

The old `municipal-data/manifest.json` key `unresolvedCandidateBlocks` now reflects **189 current unresolved**, not its historic 226 denominator. `docs/phase4-nonfield-readiness.json` retains `original_release_pending=226` and `published_before_pending_review=1668`; the readiness gate validates both quantities and fails closed when any non-field requirement remains open.

## Non-field release safety

- 1,641 new-package blocks and 2,414 new-package geometry edges, in exactly ten locality/shared-boundary packages
- The original 33 Maribyrnong previously published blocks remain present separately
- All ten static package SHA-256 digests verified against the manifest
- Source-reviewed six IDs explicitly tested for expected street/boundary identity, PFI and absence of tunnel class-0 geometries
- Non-field automated tests and exact production commit parity must be verified at merge/deployment time
- No parking-bay record, MongoDB schema, standalone terminal geometry or runtime operator override altered

**Remaining independent tasks:** 189 unresolved road blocks, 318 terminal candidates, 2,497 pending source-feature dispositions and other Phase 4 non-field acceptance requirements. `fieldTesting.authorised=false` remains mandatory. Live field tests cannot proceed. The existing release script `scripts/release_phase4_reviewed.py` publishes the original v2 audited staging snapshot only and must not overwrite the newly amended v3 source-qualified packages; future full rebuilds must explicitly incorporate the six supplementary review decisions.
