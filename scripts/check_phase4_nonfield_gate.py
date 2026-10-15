#!/usr/bin/env python3
"""Fail-closed GeoCapture Phase 4 non-field-to-field acceptance gate.

Normal CI audits recorded gate consistency and byte-exact static packages.
--require-field-ready is an explicit independent gate: it fails until every
non-field criterion has a verified evidence reference, source-only blockers
are resolved or evidenced as field-only, and the owner authorises the release.

This is a release-safety gate, NOT a substitute for independent source audit,
browser PWA integration, non-production MongoDB tests or field QA.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_CHECKS = {
    "current_package_integrity",
    "all_source_feature_dispositions",
    "all_road_block_dispositions",
    "source_terminal_classification",
    "loader_boundary_offline_cache_and_recovery",
    "local_matcher_and_operator_override_regression",
    "queued_capture_and_nonproduction_mongodb_recovery",
    "measured_nonfield_performance_p50_p95_worst",
    "final_regression_ci_and_live_sha_parity",
}
EXPECTED_PACKAGES = {
    "braybrook", "footscray", "kingsville", "maidstone", "maribyrnong",
    "seddon", "shared-localities", "tottenham", "west-footscray", "yarraville"
}
REVIEW_STATE = "OFFICIAL_SOURCE_TOPOLOGY_VERIFIED_HANDSET_QA_PENDING"


def audit(repo=ROOT, readiness=None):
    """Return (integrity_errors, field_blockers) without mutating sources."""
    repo = Path(repo)
    readiness = readiness or json.loads(
        (repo / "docs/phase4-nonfield-readiness.json").read_text(encoding="utf-8"))
    manifest = json.loads((repo / "municipal-data/manifest.json").read_text(encoding="utf-8"))
    integrity = []
    blockers = []
    inv = readiness["inventory"]
    blocks, features = inv["blocks"], inv["features"]
    if readiness.get("schema") != "geocapture.phase4.nonfield_readiness.v1":
        integrity.append("unexpected non-field readiness schema")
    if sum(blocks[k] for k in ("published", "outside", "unsupported_for_vehicular_lookup",
                                "requiring_evidence")) != blocks["total"]:
        integrity.append("candidate block dispositions do not reconcile")
    if sum(features[k] for k in ("published_associations", "outside",
                                  "unsupported_for_vehicular_lookup", "pending_review")) != features["total"]:
        integrity.append("source feature disposition counts do not reconcile")
    if blocks["original_release_pending"] != (blocks["unsupported_for_vehicular_lookup"]
                                                + blocks["requiring_evidence"]
                                                + blocks["published"] - blocks.get("published_before_pending_review", 0)):
        integrity.append("review overlay is inconsistent with published manifest snapshot")
    if manifest["unresolvedCandidateBlocks"] != blocks["requiring_evidence"]:
        integrity.append("municipal manifest and archived pending candidate count disagree")
    if blocks.get("published_before_pending_review") != 1668 or blocks["published"] < 1668:
        integrity.append("initial source qualified publication baseline is not preserved")
    if manifest["sourceQualifiedBlocks"] != blocks["published"]:
        integrity.append("reviewed municipal road block count differs from manifest")
    if manifest["sourceRoadSHA256"] != readiness["source"]["roadSHA256"]:
        integrity.append("official road source SHA drift")
    if manifest["councilPolygonSHA256"] != readiness["source"]["polygonSHA256"]:
        integrity.append("official municipality polygon SHA drift")
    if manifest.get("operationalCoverageComplete") is not False:
        integrity.append("municipal operational coverage must not be falsely certified")
    if set(manifest.get("packages", {})) != EXPECTED_PACKAGES:
        integrity.append("expected ten locality/shared packages not present")
    all_edges = set()
    edges = counted_blocks = 0
    for key, item in manifest.get("packages", {}).items():
        if key not in EXPECTED_PACKAGES:
            continue
        datafile = repo / "municipal-data" / (key + ".json")
        if item.get("file") != "./municipal-data/" + key + ".json":
            integrity.append("package path mismatch: " + key)
            continue
        if not datafile.is_file():
            integrity.append("package missing: " + key)
            continue
        raw = datafile.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            integrity.append("package SHA-256 mismatch: " + key)
            continue
        content = json.loads(raw)
        if content.get("version") != manifest["version"]:
            integrity.append("package/manifest version mismatch: " + key)
        segments = content.get("segments", [])
        if not isinstance(segments, list):
            integrity.append("invalid package segment list: " + key)
            continue
        counted_blocks += item["roadBlocks"]
        edges += len(segments)
        if len(segments) < item["roadBlocks"]:
            integrity.append("fewer edges than road blocks: " + key)
        for segment in segments:
            sid = segment.get("id")
            if not isinstance(sid, str) or sid in all_edges:
                integrity.append("duplicate/invalid geometry identity: " + str(sid))
            all_edges.add(sid)
            if (segment.get("reviewState") != REVIEW_STATE or
                    segment.get("from") == "DEAD END" or segment.get("to") == "DEAD END"):
                integrity.append("unverified road intersection/terminal in pack: " + str(sid))
            if segment.get("attribution", {}).get("snapshotSHA256") != manifest["sourceRoadSHA256"]:
                integrity.append("source attribution mismatch: " + str(sid))
            if 2 in segment.get("vicmapClassCodes", []) and (segment.get("positive") or segment.get("negative")):
                integrity.append("unverified class-2 cardinal side published: " + str(sid))
    if edges != manifest["newGeometryEdges"] or counted_blocks != manifest["newSourceQualifiedRoadBlocks"]:
        integrity.append("manifest road block / geometry edge totals mismatch")
    checks = readiness.get("checks", {})
    if set(checks) != REQUIRED_CHECKS:
        integrity.append("non-field acceptance check set is missing or unexpected")
    for key in sorted(REQUIRED_CHECKS):
        detail = checks.get(key, {})
        state = detail.get("status")
        if state not in ("verified", "pending"):
            integrity.append("invalid acceptance state for " + key)
        if state == "verified" and not detail.get("evidence"):
            integrity.append("missing evidence for verified criterion " + key)
        if state != "verified":
            blockers.append(key)
    # For a field-only verification dependency, record an auditable candidate
    # disposition: an open generic source-reconciliation task is NOT field-only.
    if blocks["requiring_evidence"]:
        blockers.append(str(blocks["requiring_evidence"]) + " road-block candidates need disposition")
    if features["pending_review"]:
        blockers.append(str(features["pending_review"]) + " source features need disposition")
    if inv["conflicting_review_reason_candidates"]:
        blockers.append(str(inv["conflicting_review_reason_candidates"]) + " dual-reason review conflicts")
    if not all(readiness["restrictions"].values()):
        integrity.append("source safety restrictions must remain enabled")
    granted = readiness.get("fieldTesting", {}).get("authorised") is True
    if granted and (blockers or integrity):
        integrity.append("field testing marked authorised while non-field checks remain open")
    if not granted:
        blockers.append("owner field-testing authorisation not granted")
    if granted and not readiness.get("fieldTesting", {}).get("authorisationEvidence"):
        integrity.append("missing field-testing authorisation evidence")
    return integrity, blockers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-field-ready", action="store_true",
                        help="fail unless all non-field metrics integrated and field gate explicitly authorised")
    args = parser.parse_args()
    errors, blockers = audit()
    print("GeoCapture Phase 4 non-field integrity:", "PASS" if not errors else "FAILED")
    print("Physical field testing:", "BLOCKED" if blockers or errors else "AUTHORISED")
    for error in errors:
        print("INTEGRITY:", error)
    for blocker in blockers:
        print("BLOCKER:", blocker)
    if errors:
        return 1
    if args.require_field_ready and blockers:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
