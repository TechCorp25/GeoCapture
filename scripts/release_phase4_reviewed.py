#!/usr/bin/env python3
"""Source-locked release of separately reviewed Maribyrnong road blocks.

Only qualified intersections independently revalidated against the exact
original Vicmap road and LGA sources may enter the mobile data pack.
Never publishes pending, crossing, dead-end candidates, or captured bay data.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from scripts.audit_municipal_candidates import audit_one, graph_features, validate_boundary, EXTENDED_VEHICULAR_CLASSES
from scripts.build_municipal_road_pack import build
from scripts.maribyrnong_inventory import line_membership

PINNED_ROAD_SHA = "3f5a4ee47b7e86cff22df5e82efde6afa866eacf42f07ad8b87fce2a944412bb"
PINNED_LGA_SHA = "d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb"
ROAD_URL = "https://discover.data.vic.gov.au/en_AU/dataset/vicmap-transport-road-line"
REVIEW_STATE = "OFFICIAL_SOURCE_TOPOLOGY_VERIFIED_HANDSET_QA_PENDING"
MINIMUM_BLOCKS = 1454
VERSION = "maribyrnong-phase4-20261015-v2"


def read_checked(folder, filename, expected_sha):
    raw = (folder / filename).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha:
        raise ValueError(filename + ": source checksum mismatch: " + actual)
    return json.loads(raw)


def release(folder, destination, baseline):
    road_manifest = json.loads((folder / "roads-manifest.json").read_text())
    council_manifest = json.loads((folder / "lga-manifest.json").read_text())
    if road_manifest.get("sha256") != PINNED_ROAD_SHA or not road_manifest.get("paginationVerified"):
        raise ValueError("Not the reviewed municipality-wide, complete TR_ROAD source snapshot")
    if council_manifest.get("sha256") != PINNED_LGA_SHA:
        raise ValueError("Not the independently reviewed Maribyrnong polygon")
    source = read_checked(folder, "roads.geojson", PINNED_ROAD_SHA)
    boundary_doc = read_checked(folder, "lga.geojson", PINNED_LGA_SHA)
    council = validate_boundary(boundary_doc, council_manifest, (folder / "lga.geojson").read_bytes())
    if len(source.get("features", [])) != road_manifest["officialObjectIdCount"]:
        raise ValueError("Official object-ID count mismatch")
    by_pfi, nodes = graph_features(source)
    permitted = json.loads((folder / "staging-packages" / "manifest.json").read_text())
    expected_blocks = permitted.get("stagedCandidates")
    if not isinstance(expected_blocks, int) or not MINIMUM_BLOCKS <= expected_blocks <= 2000 or permitted.get("totalQualified",0) < 1487:
        raise ValueError("Unexpected expanded-source staging denominator")
    if permitted.get("sourceRoadSHA256") != PINNED_ROAD_SHA or permitted.get("sourceLGASHA256") != PINNED_LGA_SHA:
        raise ValueError("Staging source provenance changed")
    existing = set()
    for file in baseline:
        for f in json.loads(Path(file).read_text())["features"]:
            p = f.get("properties") or {}
            existing.add(str(p.get("vicmapPFI")))
    if len(existing) != 33:
        raise ValueError("Must preserve exactly 33 separately published municipal PFIs")
    output = {}
    all_ids = set()
    all_pfis = set()
    total_edges = 0
    for name, spec in sorted(permitted["packages"].items()):
        if name != Path(name).name or "/" in name or "\\" in name:
            raise ValueError("Invalid locality package name")
        path = folder / "staging-packages" / spec["file"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
            raise ValueError("Locality package checksum mismatch: " + name)
        features = json.loads(raw).get("features") or []
        if len(features) != spec["candidateBlocks"]:
            raise ValueError("Locality block inventory changed")
        for f in features:
            p = f.get("properties") or {}
            fid = p.get("roadSegmentId")
            pfis = list(map(str, p.get("vicmapPFIs") or []))
            if not fid or fid in all_ids or not pfis or set(pfis) & (existing | all_pfis):
                raise ValueError("Duplicate/previously released block identity or source PFI")
            all_ids.add(fid)
            all_pfis.update(pfis)
            if p.get("boundaryEndpointsVerified") is not True or p.get("packageReviewState") != "STAGED_OFFLINE_NOT_PUBLISHED":
                raise ValueError("Unreviewed or previously rejected municipal road candidate")
            if p.get("roadSourceSHA256") != PINNED_ROAD_SHA or p.get("councilSourceSHA256") != PINNED_LGA_SHA:
                raise ValueError("Candidate does not trace to immutable official source")
            if line_membership(f["geometry"]["coordinates"], council) != "INSIDE":
                raise ValueError("Candidate not wholly within official council polygon")
            pending = json.loads(json.dumps(f))
            pending["properties"]["boundaryEndpointsVerified"] = False
            result, why = audit_one(pending, by_pfi, nodes, council, road_manifest["bboxWGS84"],
                                    valid_classes=EXTENDED_VEHICULAR_CLASSES)
            if result != "ELIGIBLE":
                raise ValueError("Independent source topology no longer validates " + str(fid) + ": " + why)
        segments, skipped = build({"type": "FeatureCollection", "features": features},
                                  "maribyrnong", "State of Victoria — Vicmap Transport TR_ROAD",
                                  "CC BY 4.0", ROAD_URL)
        if skipped or not segments:
            raise ValueError("Road package failed the strict verified segment builder: " + str(skipped))
        block_by_id = {f["properties"]["roadSegmentId"]: f["properties"] for f in features}
        for segment in segments:
            block = segment["id"].split(":")[1]
            props = block_by_id[block]
            segment["sourcePFIs"] = props["vicmapPFIs"]
            segment["vicmapClassCodes"] = sorted({int(by_pfi[str(i)]["properties"]["class_code"])
                                                 for i in props["vicmapPFIs"]})
            # Class-2 arterials can include parallel/divided carriageways.
            # The road/intersections are source-verified but no cardinal
            # side may be inferred before device/field corroboration.
            if any(by_pfi[str(i)]["properties"].get("class_code") == 2
                   for i in props["vicmapPFIs"]):
                segment["positive"] = ""
                segment["negative"] = ""
            segment["reviewState"] = REVIEW_STATE
            segment["attribution"]["snapshotSHA256"] = PINNED_ROAD_SHA
            segment["attribution"]["councilPolygonSHA256"] = PINNED_LGA_SHA
            segment["attribution"]["reviewState"] = REVIEW_STATE
        total_edges += len(segments)
        encoded = (json.dumps({"version": VERSION,
                                "segments": segments}, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        outfile = name + ".json"
        output[outfile] = encoded
    if len(all_ids) != expected_blocks or sum(p["candidateBlocks"] for p in permitted["packages"].values()) != expected_blocks:
        raise ValueError("Qualified block count changed unexpectedly")
    if total_edges < expected_blocks:
        raise ValueError("Corrupted edge pack")
    manifest = {
        "schema": "geocapture.municipal_road_packs.v1",
        "municipality": "CITY OF MARIBYRNONG",
        "version": VERSION,
        "sourceRoadSHA256": PINNED_ROAD_SHA,
        "councilPolygonSHA256": PINNED_LGA_SHA,
        "licence": "CC BY 4.0", "attribution": "State of Victoria",
        "publicationReviewState": REVIEW_STATE,
        "operationalCoverageComplete": False,
        "publishedExistingRoadBlocks": len(existing),
        "newSourceQualifiedRoadBlocks": expected_blocks,
        "newGeometryEdges": total_edges,
        "unresolvedCandidateBlocks": 407,  # overridden below from the fresh independent audit
        "unverifiedDeadEndsDoNotMatch": True,
        "packages": {}
    }
    fresh = json.loads((folder / "municipal-inventory-report.json").read_text())
    manifest["unresolvedCandidateBlocks"] = fresh["candidateFinalDispositions"].get("PENDING_REVIEW", 0)
    manifest["sourceQualifiedBlocks"] = fresh["candidateFinalDispositions"].get("VERIFIED", 0)
    manifest["reviewedVicmapClasses"] = sorted(EXTENDED_VEHICULAR_CLASSES)
    for name, spec in sorted(permitted["packages"].items()):
        filename = name + ".json"
        manifest["packages"][name] = {
            "file": "./municipal-data/" + filename,
            "boundsWGS84": spec["boundsWGS84"],
            "roadBlocks": spec["candidateBlocks"],
            "sha256": hashlib.sha256(output[filename]).hexdigest()
        }
    destination.mkdir(parents=True, exist_ok=True)
    existing_manifest = destination / "manifest.json"
    if existing_manifest.exists():
        installed_version = json.loads(existing_manifest.read_text(encoding="utf-8")).get("version")
        if installed_version != VERSION:
            raise ValueError("Refusing to overwrite supplemental source-reviewed release with legacy staging builder")
    for filename, value in output.items():
        (destination / filename).write_bytes(value)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "packages"}, indent=2))
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--published", action="append", type=Path, required=True)
    args = p.parse_args()
    release(args.audit, args.output, args.published)


if __name__ == "__main__":
    main()
