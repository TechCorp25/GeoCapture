#!/usr/bin/env python3
"""Stage auditable, non-published locality packages from Phase 4 source audit.

Staging is not approval to deploy. Shared-boundary, duplicate-PFI and already
published blocks are kept out of new locality payloads.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

CANONICAL_LOCALITIES = {
    "FOOTSCRAY", "WEST FOOTSCRAY", "SEDDON", "YARRAVILLE", "KINGSVILLE",
    "MAIDSTONE", "MARIBYRNONG", "BRAYBROOK", "TOTTENHAM",
}


def stage(source_qualified, ledger, road_hash, lga_hash):
    records = {r["candidateId"]: r for r in ledger}
    qualified = source_qualified.get("features") or []
    if len({f["properties"]["roadSegmentId"] for f in qualified}) != len(qualified):
        raise ValueError("Duplicate qualified road-block candidate ID")
    duplicate_pf = Counter(str(pfi) for f in qualified
                           for pfi in f["properties"].get("vicmapPFIs", []))
    grouped, exceptions = defaultdict(list), []
    for f in qualified:
        p = f.get("properties") or {}
        identifier = p.get("roadSegmentId")
        reference = records.get(identifier)
        if not reference or reference.get("topologyAuditStatus") != "ELIGIBLE":
            raise ValueError("Cannot stage a feature absent from independent audit")
        if reference.get("municipalityMembership") != "INSIDE":
            exceptions.append({"id": identifier, "reason": "not_fully_contained_in_lga"})
            continue
        if reference.get("publicationStatus") == "PUBLISHED_PREVIOUS_PHASE":
            exceptions.append({"id": identifier, "reason": "previously_published_do_not_duplicate"})
            continue
        ids = list(map(str, p.get("vicmapPFIs") or []))
        if not ids or any(duplicate_pf[i] > 1 for i in ids):
            exceptions.append({"id": identifier, "reason": "shared_source_pfi_requires_review"})
            continue
        localities = sorted(set(str(x).upper() for x in p.get("suburbs") or []))
        approved = [loc for loc in localities if loc in CANONICAL_LOCALITIES]
        if not approved:
            exceptions.append({"id": identifier, "reason": "unmapped_locality_requires_review",
                               "localities": localities})
            continue
        # Never duplicate a cross-locality road block: route it to one
        # deterministic shared-boundary package retaining its real localities.
        bucket = approved[0].lower().replace(" ", "-") if len(approved) == 1 else "shared-localities"
        staged = json.loads(json.dumps(f))
        staged["properties"]["packageReviewState"] = "STAGED_OFFLINE_NOT_PUBLISHED"
        staged["properties"]["roadSourceSHA256"] = road_hash
        staged["properties"]["councilSourceSHA256"] = lga_hash
        staged["properties"]["sourceLicence"] = "CC BY 4.0"
        staged["properties"]["sourceAttribution"] = "State of Victoria — Vicmap Transport TR_ROAD"
        grouped[bucket].append(staged)
    if sum(map(len, grouped.values())) + len(exceptions) != len(qualified):
        raise AssertionError("Staging lost audited source candidates")
    manifest = {
        "municipality": "MARIBYRNONG", "version": "phase4-staging-20261015",
        "sourceRoadSHA256": road_hash, "sourceLGASHA256": lga_hash,
        "totalQualified": len(qualified),
        "stagedCandidates": sum(map(len, grouped.values())),
        "excludedFromStaging": len(exceptions),
        "reviewGate": "STAGING_ONLY_UNAPPROVED_NEVER_LOAD_AS_PRODUCTION",
        "packages": {},
    }
    packages = {}
    for group, features in sorted(grouped.items()):
        features.sort(key=lambda f: f["properties"]["roadSegmentId"])
        result = {"type": "FeatureCollection", "features": features}
        encoded = (json.dumps(result, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        points = [point for f in features for point in f["geometry"]["coordinates"]]
        manifest["packages"][group] = {
            "candidateBlocks": len(features),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "boundsWGS84": [min(p[0] for p in points), min(p[1] for p in points),
                            max(p[0] for p in points), max(p[1] for p in points)],
            "file": group + ".geojson"
        }
        packages[group] = encoded
    return packages, exceptions, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("eligible", "candidate-ledger", "source-manifest", "lga-manifest", "output-dir"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    def read(path):
        return json.loads(Path(path).read_text())
    a = read(args.source_manifest)
    b = read(args.lga_manifest)
    if not a.get("paginationVerified") or a.get("licence") != "CC BY 4.0":
        raise ValueError("Unverified official municipal road source")
    packs, exceptions, report = stage(read(args.eligible), read(args.candidate_ledger),
                                      a["sha256"], b["sha256"])
    folder = Path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    for group, content in packs.items():
        (folder / (group + ".geojson")).write_bytes(content)
    (folder / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    (folder / "requires-review.json").write_text(json.dumps(exceptions, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
