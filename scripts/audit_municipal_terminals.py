#!/usr/bin/env python3
"""Independent OFFLINE terminal-road investigation queue for Maribyrnong.

An official UFI degree-one node suggests a network terminal, but is NEVER
sufficient by itself to certify a physical dead end. Only an externally
corroborated, separately reviewed terminal may be published.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from scripts.audit_municipal_candidates import (
    graph_features, in_boundary, norm, validate_boundary, EXTENDED_VEHICULAR_CLASSES
)
from scripts.maribyrnong_inventory import line_membership


def terminal_candidates(source, council, source_sha, lga_sha, published_pf=None):
    by_pfi, nodes = graph_features(source)
    prior = set(published_pf or ())  # pairs (source PFI, exact reviewed terminal UFI)
    rows = []
    seen = set()
    counts = Counter()
    for pfi, f in sorted(by_pfi.items(), key=lambda item: item[0]):
        p = f["properties"]
        g = f["geometry"]
        if (norm(p.get("feature_type_code")) != "ROAD" or
            norm(p.get("road_status")) != "O" or
            str(p.get("vehicular_access")) != "1" or
            p.get("class_code") not in EXTENDED_VEHICULAR_CLASSES or
            p.get("structure_name") or
            not norm(p.get("ezi_road_name")) or
            norm(p.get("ezi_road_name")) in {"UNNAMED", "NOT NAMED", "UNKNOWN"}):
            continue
        coords=g["coordinates"]
        if line_membership(coords,council)!="INSIDE":
            continue
        for key, pt in (("from_ufi",coords[0]),("to_ufi",coords[-1])):
            ufi=p.get(key)
            if ufi in (None,0,"0",""):
                counts["no_valid_ufi"]+=1
                continue
            node=str(ufi)
            if len(nodes.get(node,[])) != 1 or not in_boundary(pt,council):
                continue
            identity="terminal:"+node+":"+norm(p.get("ezi_road_name")).replace(" ","-")
            if identity in seen: continue
            seen.add(identity)
            # A source node can look terminal if the network is incomplete or
            # a bridge/structure is represented separately. Record, do not infer.
            adjacent_to_other = []
            other=p.get("to_ufi") if key=="from_ufi" else p.get("from_ufi")
            if other not in (None,0,"0",""):
                adjacent_to_other = sorted({norm(x["properties"].get("ezi_road_name"))
                    for x,_ in nodes.get(str(other),[]) if
                    norm(x["properties"].get("ezi_road_name")) != norm(p.get("ezi_road_name"))})
            # This is only the nearest edge's opposite UFI, not automatically
            # a true block boundary. Preserve all ambiguity for human review.
            previously_approved = (pfi, node) in prior
            status = "FIELD_VERIFIED_REFERENCE" if previously_approved else "PENDING_FIELD_CONFIRMATION"
            reason = ("separately_reviewed_existing_Talbot_reference" if previously_approved
                      else "official_degree_one_UFI_requires_physical_terminal_and_bounding_intersection_confirmation")
            rows.append({
                "candidateId":identity,"street":norm(p.get("ezi_road_name")),
                "sourcePFI":pfi,"terminalUFI":node,"connectedUFI":str(other or ""),
                "terminalPositionWGS84":pt,"featureLocalities":sorted({
                    norm(p.get(k)) for k in ("left_locality","right_locality") if norm(p.get(k))}),
                "adjacentStreetNamesAtNextSourceUFI":adjacent_to_other,
                "status":status,"reason":reason,
                "officialTopologyDegree":1,
                "physicalDeadEndVerified":bool(previously_approved),
                "boundaryEndpointsVerified":bool(previously_approved),
                "publicationStatus":"PUBLISHED_PREVIOUS_PHASE" if previously_approved else "NOT_PUBLISHED",
                "sourceRoadSha256":source_sha,"councilPolygonSha256":lga_sha
            })
            counts[status]+=1
    report={
        "municipality":"MARIBYRNONG","terminalReviewCandidates":len(rows),
        "dispositions":dict(sorted(counts.items())),
        "basis":"Official source network UFI degree one, complete buffered Vicmap snapshot and LGA",
        "networkEndpointAloneEstablishesDeadEnd":False,
        "independentFieldReviewRequired":True,
        "publicationApproved":False,
        "sourceRoadSHA256":source_sha,"councilPolygonSHA256":lga_sha
    }
    if len({r["candidateId"] for r in rows})!=len(rows):
        raise ValueError("Duplicate municipal terminal identity")
    return rows,report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ("source","source-manifest","boundary","boundary-manifest","output","report"):
        ap.add_argument("--"+k,required=True)
    ap.add_argument("--published",action="append",default=[])
    args=ap.parse_args()
    def checked(source, manifest):
        m=json.loads(Path(manifest).read_text())
        raw=Path(source).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=m.get("sha256"):
            raise ValueError("Corrupt official source")
        return json.loads(raw),m
    road,rm=checked(args.source,args.source_manifest)
    boundary_doc,lm=checked(args.boundary,args.boundary_manifest)
    if not rm.get("paginationVerified"):
        raise ValueError("Incomplete buffered transport snapshot")
    council=validate_boundary(boundary_doc,lm,Path(args.boundary).read_bytes())
    approved=set()
    source_by_pfi,_=graph_features(road)
    for path in args.published:
        for feature in json.loads(Path(path).read_text())["features"]:
            p=feature.get("properties") or {}
            if p.get("boundaryEndpointsVerified") is not True:
                continue
            # Only a separately corroborated DEAD END reference may mark its
            # exact official terminal UFI verified. The other endpoint must
            # NOT inherit certification merely by sharing its source PFI.
            if p.get("to") != "DEAD END" and p.get("from") != "DEAD END":
                continue
            pfi=str(p.get("vicmapPFI"))
            original=source_by_pfi.get(pfi)
            if not original:
                raise ValueError("Existing reviewed terminal PFI absent from official network")
            import math
            reviewed=feature["geometry"]["coordinates"]
            terminal=reviewed[-1] if p.get("to")=="DEAD END" else reviewed[0]
            official=original["geometry"]["coordinates"]
            matches=[]
            for key,coord in (("from_ufi",official[0]),("to_ufi",official[-1])):
                if math.hypot((terminal[0]-coord[0])*88000,(terminal[1]-coord[1])*111000) < 2:
                    matches.append(str(original["properties"][key]))
            if len(matches)!=1:
                raise ValueError("Ambiguous reviewed dead-end endpoint")
            approved.add((pfi,matches[0]))
    candidates,report=terminal_candidates(road,council,rm["sha256"],lm["sha256"],approved)
    for filename,value in ((args.output,candidates),(args.report,report)):
        p=Path(filename);p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
