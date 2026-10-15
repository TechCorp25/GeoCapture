#!/usr/bin/env python3
"""Fail-closed whole-LGA Vicmap road-feature and candidate reconciliation.

All non-published roads remain explicit in the inventory. No automatic
production approval; does not contain operator GPS or parking-bay records.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from scripts.audit_municipal_candidates import in_boundary, validate_boundary

UNNAMED = {"", "UNNAMED", "NOT NAMED", "UNKNOWN", "NONE"}


def norm(s):
    return " ".join(str(s or "").upper().split())


def orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(a, b, c):
    return (min(a[0], b[0]) - 1e-10 <= c[0] <= max(a[0], b[0]) + 1e-10
            and min(a[1], b[1]) - 1e-10 <= c[1] <= max(a[1], b[1]) + 1e-10
            and abs(orient(a, b, c)) <= 1e-10)


def crosses(a, b, c, d):
    x, y, z, w = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if ((x > 0 > y or x < 0 < y) and (z > 0 > w or z < 0 < w)):
        return True
    return any((abs(x) <= 1e-10 and on_segment(a, b, c),
                abs(y) <= 1e-10 and on_segment(a, b, d),
                abs(z) <= 1e-10 and on_segment(c, d, a),
                abs(w) <= 1e-10 and on_segment(c, d, b)))


def polygon_rings(boundary):
    polygons = ([boundary["coordinates"]] if boundary["type"] == "Polygon"
                else boundary["coordinates"])
    return [ring for polygon in polygons for ring in polygon]


def line_membership(line, boundary):
    """Return INSIDE, CROSSING or OUTSIDE including holes and edge-touch."""
    if not line or len(line) < 2 or any(len(p) < 2 for p in line):
        return "INVALID"
    hits = [in_boundary(p, boundary) for p in line]
    boundary_touch = any(
        crosses(a, b, c, d)
        for a, b in zip(line, line[1:])
        for ring in polygon_rings(boundary)
        for c, d in zip(ring, ring[1:])
    )
    if boundary_touch or (any(hits) and not all(hits)):
        return "CROSSING"
    if all(hits):
        return "INSIDE"
    return "OUTSIDE"


def source_pfi(feature):
    return str((feature.get("properties") or {}).get("pfi") or "")


def validated_reference(reference, official):
    """Old publication is corroboration only if its source geometry still agrees."""
    published = reference.get("geometry") or {}
    source = official.get("geometry") or {}
    source_line = source.get("coordinates") or []
    reviewed_line = published.get("coordinates") or []
    # Phase 3 validated paths are sometimes ordered junction-to-junction in
    # reverse of the source PFI axis; reversal preserves the same geometry.
    same_line = reviewed_line == source_line or reviewed_line == list(reversed(source_line))
    return (published.get("type") == source.get("type") == "LineString"
            and same_line and len(source_line) >= 2
            and (reference.get("properties") or {}).get("boundaryEndpointsVerified") is True)


def reconcile(source, boundary, candidates, dispositions, published, road_sha, lga_sha):
    features = source.get("features") or []
    if source.get("type") != "FeatureCollection" or not features:
        raise ValueError("Empty or invalid official road source")
    indexed = {}
    for f in features:
        pfi = source_pfi(f)
        if not pfi or pfi in indexed:
            raise ValueError("Missing or repeated source PFI")
        indexed[pfi] = f
    published_by_pfi = {}
    for f in published:
        p = f.get("properties") or {}
        pfi = str(p.get("vicmapPFI") or "")
        if not pfi or pfi in published_by_pfi:
            raise ValueError("Duplicate or unidentified published road PFI")
        published_by_pfi[pfi] = f
    if len(dispositions) != len(candidates.get("features") or []):
        raise ValueError("Candidate disposition count does not match candidate inventory")
    candidate_by_pfi = defaultdict(list)
    candidate_ledger = []
    for candidate, decision in zip(candidates["features"], dispositions):
        p = candidate.get("properties") or {}
        if p.get("roadSegmentId") != decision.get("roadSegmentId"):
            raise ValueError("Candidate identities do not match audit dispositions")
        ids = list(map(str, p.get("vicmapPFIs") or []))
        if not ids or any(i not in indexed for i in ids):
            raise ValueError("Candidate references missing original PFI")
        for identifier in ids:
            candidate_by_pfi[identifier].append(p.get("roadSegmentId"))
        membership = line_membership((candidate.get("geometry") or {}).get("coordinates") or [], boundary)
        previously_published = bool(ids and all(identifier in published_by_pfi for identifier in ids))
        if membership == "OUTSIDE":
            disposition, reason = "OUT_OF_SCOPE", "wholly_outside_official_municipal_polygon"
        elif membership == "INVALID":
            disposition, reason = "AMBIGUOUS", "invalid_candidate_geometry"
        elif decision.get("status") == "REJECT":
            disposition, reason = "REJECTED", decision.get("reason")
        elif decision.get("status") == "ELIGIBLE":
            disposition, reason = "VERIFIED", decision.get("reason")
        else:
            disposition, reason = "PENDING_REVIEW", decision.get("reason")
        candidate_ledger.append({
            "candidateId": p.get("roadSegmentId"), "sourcePFIs": ids,
            "street": p.get("street"), "between": [p.get("from"), p.get("to")],
            "topologyAuditStatus": decision.get("status"),
            "municipalityMembership": membership,
            "disposition": disposition,
            "reason": reason,
            "publicationStatus": "PUBLISHED_PREVIOUS_PHASE" if previously_published else "STAGED_NOT_PUBLISHED",
            "boundaryEndpointsVerified": False,
        })
    endpoint_counts = Counter()
    for f in features:
        p = f.get("properties") or {}
        for key in ("from_ufi", "to_ufi"):
            if p.get(key) not in (None, "", 0, "0"):
                endpoint_counts[str(p[key])] += 1
    ledger, statuses, memberships = [], Counter(), Counter()
    for pfi, f in sorted(indexed.items(), key=lambda kv: kv[0]):
        p, g = f["properties"], f.get("geometry") or {}
        coords = g.get("coordinates") or []
        membership = (line_membership(coords, boundary)
                      if g.get("type") == "LineString" else "INVALID")
        memberships[membership] += 1
        name = norm(p.get("ezi_road_name"))
        official_road = norm(p.get("feature_type_code")) == "ROAD"
        source_ref = published_by_pfi.get(pfi)
        still_verified = bool(source_ref and validated_reference(source_ref, f)
                              and membership == "INSIDE")
        if membership == "OUTSIDE":
            status, reason = "OUT_OF_SCOPE", "within_buffer_outside_council"
        elif membership == "INVALID":
            status, reason = "AMBIGUOUS", "unsupported_or_invalid_source_geometry"
        elif membership == "CROSSING":
            status, reason = "PENDING_REVIEW", "crosses_municipal_boundary"
        elif not official_road or name in UNNAMED:
            status, reason = "UNSUPPORTED", "unnamed_or_non_road_feature"
        elif still_verified:
            status, reason = "VERIFIED", "previously_published_geometry_matches_source"
        elif source_ref:
            status, reason = "PENDING_REVIEW", "published_source_geometry_needs_reconciliation"
        elif pfi in candidate_by_pfi:
            status, reason = "PENDING_REVIEW", "candidate_requires_individual_release_review"
        else:
            status, reason = "PENDING_REVIEW", "no_validated_road_block_candidate"
        statuses[status] += 1
        degree = [endpoint_counts.get(str(p.get(x)), 0) for x in ("from_ufi", "to_ufi")]
        ledger.append({
            "sourcePFI": pfi, "sourceObjectId": p.get("id"),
            "networkUFI": [p.get("from_ufi"), p.get("to_ufi")],
            "street": name, "localities": sorted(set(norm(p.get(k)) for k in
                           ("left_locality", "right_locality") if norm(p.get(k)))),
            "municipalityMembership": membership, "featureType": p.get("feature_type_code"),
            "classCode": p.get("class_code"), "roadStatus": p.get("road_status"),
            "vehicularAccess": p.get("vehicular_access"),
            "candidateIds": sorted(set(candidate_by_pfi.get(pfi, []))),
            "possibleTerminalEndpointUFI": [p.get(x) for x, count in zip(
                ("from_ufi", "to_ufi"), degree) if count == 1],
            "status": status, "reason": reason,
            "publicationStatus": "PUBLISHED_PREVIOUS_PHASE" if source_ref else "NOT_PUBLISHED",
            "referenceGeometryMatchesCurrentSource": still_verified,
            "sourceSha256": road_sha, "lgaSha256": lga_sha
        })
    absent = sorted(set(published_by_pfi) - set(indexed))
    if absent:
        raise ValueError("Published PFIs absent from new municipality source: " + str(absent[:10]))
    in_scope = statuses["VERIFIED"] + statuses["PENDING_REVIEW"] + statuses["UNSUPPORTED"] + statuses["AMBIGUOUS"]
    candidate_dispositions = Counter(item["disposition"] for item in candidate_ledger)
    localities = Counter(loc for row in ledger if row["municipalityMembership"] != "OUTSIDE"
                         for loc in row["localities"])
    report = {
        "municipality": "CITY OF MARIBYRNONG", "sourceRoadSha256": road_sha,
        "sourceLGASha256": lga_sha, "sourceRoadFeatureCount": len(features),
        "roadMembershipCounts": dict(sorted(memberships.items())),
        "roadDispositionCounts": dict(sorted(statuses.items())),
        "roadFeaturesNotOutOfScope": in_scope, "roadCandidateCount": len(candidate_ledger),
        "candidateAuditCounts": dict(Counter(d.get("status") for d in dispositions)),
        "candidateFinalDispositions": dict(sorted(candidate_dispositions.items())),
        "localityFeaturePresence": dict(sorted(localities.items())),
        "previouslyPublishedPFIs": len(published_by_pfi),
        "previouslyPublishedGeometryMatched": sum(x["referenceGeometryMatchesCurrentSource"] for x in ledger),
        "completeCoverageClaim": False,
        "unresolvedRoadFeatures": statuses["PENDING_REVIEW"] + statuses["AMBIGUOUS"],
        "releaseGate": "SOURCE_INVENTORY_ONLY_NOT_FOR_PRODUCTION",
        "definition": "All original source features classified; coverage requires individual road-block review and field QA"
    }
    if len(ledger) != len(features) or sum(statuses.values()) != len(features):
        raise AssertionError("Municipal feature ledger has unreconciled source features")
    return ledger, candidate_ledger, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "source-manifest", "boundary", "boundary-manifest",
                 "candidates", "dispositions", "output", "candidate-ledger", "report"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--published", action="append", default=[])
    args = parser.parse_args()
    def verified_json(path, manifest):
        raw = Path(path).read_bytes()
        meta = json.loads(Path(manifest).read_text())
        if hashlib.sha256(raw).hexdigest() != meta.get("sha256"):
            raise ValueError("Source checksum mismatch: " + path)
        return json.loads(raw), meta
    source, s_manifest = verified_json(args.source, args.source_manifest)
    boundary_doc, b_manifest = verified_json(args.boundary, args.boundary_manifest)
    boundary = validate_boundary(boundary_doc, b_manifest, Path(args.boundary).read_bytes())
    if not s_manifest.get("paginationVerified"):
        raise ValueError("Phase 4 whole-LGA snapshot requires official ID completeness verification")
    publication = []
    for path in args.published:
        publication.extend(json.loads(Path(path).read_text())["features"])
    rows, candidates, report = reconcile(source, boundary,
        json.loads(Path(args.candidates).read_text()),
        json.loads(Path(args.dispositions).read_text()), publication,
        s_manifest["sha256"], b_manifest["sha256"])
    for path, data in ((args.output, rows), (args.candidate_ledger, candidates),
                       (args.report, report)):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
