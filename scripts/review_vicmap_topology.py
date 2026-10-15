#!/usr/bin/env python3
"""Inspect official Vicmap road-network topology and emit REVIEW-ONLY road-block candidates.

This is not a source of approved between-street names. Every generated
feature has boundaryEndpointsVerified=false; the production builder rejects it.
Only connected named intersections are considered. Overpasses, branches,
multiple cross-street names and missing/boundary geometry are excluded.
"""
import argparse
from collections import defaultdict, Counter
import json
import math
from pathlib import Path

def norm(value):
    return " ".join(str(value or "").upper().strip().split())
def point(coords):
    return tuple(float(x) for x in coords[:2])
def metres(a,b):
    x=(a[0]-b[0])*111000*math.cos(math.radians((a[1]+b[1])/2))
    y=(a[1]-b[1])*111000
    return math.hypot(x,y)

def road_graph(doc):
    edges=[]
    rejected=Counter()
    # Coordinate snapping is only used as a fallback for source records
    # without valid network-endpoint IDs. It does not declare road crossings.
    for feat in doc.get("features",[]):
        p=feat.get("properties") or {}
        shape=feat.get("geometry") or {}
        name=norm(p.get("ezi_road_name") or
                  (str(p.get("road_name") or "")+" "+str(p.get("road_type") or "")))
        geom=shape.get("coordinates") or []
        if not name or name in {"NOT NAMED","UNNAMED","UNKNOWN","NONE"}:
            # Still include unnamed roads in network topology where geometry exists.
            name=""
        if shape.get("type")!="LineString" or len(geom)<2:
            rejected["unsupported_geometry"]+=1
            continue
        try:
            coords=[point(x) for x in geom]
            if any(not all(math.isfinite(z) for z in pt) for pt in coords):
                raise ValueError()
        except (ValueError,TypeError):
            rejected["invalid_geometry"]+=1
            continue
        id_ = p.get("pfi") or p.get("ufi") or p.get("id") or feat.get("id")
        if not id_:
            rejected["missing_id"]+=1
            continue
        # Ignore transport-only features and grade-separated structure candidates;
        # they are reviewed separately, never guessed as physical junctions.
        structure=norm(p.get("structure_name"))
        if structure:
            rejected["named_structure"]+=1
            continue
        def key(which, at):
            ufi=p.get(which)
            if ufi is not None and str(ufi).strip() not in {"","0","None"}:
                return "ufi:"+str(ufi)
            return "xy:"+str(round(at[0],5))+","+str(round(at[1],5))
        a=key("from_ufi", coords[0])
        b=key("to_ufi", coords[-1])
        if a==b:
            rejected["loop_edge"]+=1
            continue
        edges.append({"id":str(id_),"name":name,"coords":coords,"a":a,"b":b,
                      "attributes":p})
    nodes=defaultdict(list)
    for idx,e in enumerate(edges):
        nodes[e["a"]].append(idx);nodes[e["b"]].append(idx)
    # Verify network node coordinates are not accidentally shared by distant
    # roads (invalid UFI reuse or wrong geometry orientation).
    points=defaultdict(list)
    for e in edges:
        points[e["a"]].append(e["coords"][0])
        points[e["b"]].append(e["coords"][-1])
    corrupt={node for node,pts in points.items() if any(metres(pts[0],x)>5 for x in pts[1:])}
    return edges,nodes,corrupt,rejected

def derive_candidates(doc,bbox=None):
    edges,nodes,corrupt,rejected=road_graph(doc)
    candidates=[]
    reasons=Counter(rejected)
    emitted=set()
    def crossing(street,node):
        if node in corrupt: return None,"inconsistent_node_geometry"
        names={edges[i]["name"] for i in nodes[node] if edges[i]["name"] and edges[i]["name"] !=street}
        unnamed=any(not edges[i]["name"] for i in nodes[node])
        if len(names)==1 and not unnamed:
            return next(iter(names)),None
        if len(names)>1:
            return None,"multiple_cross_streets"
        if unnamed:
            return None,"unnamed_connection"
        return None,None
    def within(at):
        if not bbox:return True
        x,y=at
        minx,miny,maxx,maxy=bbox
        return minx+.001 < x < maxx-.001 and miny+.001 < y < maxy-.001

    # Build between-street paths starting only at recognized named intersections.
    for street in sorted({e["name"] for e in edges if e["name"]}):
        relevant=[(node,crossing(street,node)[0]) for node in nodes
                  if crossing(street,node)[0] and any(edges[i]["name"]==street for i in nodes[node])]
        for start,from_name in relevant:
            for first in [idx for idx in nodes[start] if edges[idx]["name"]==street]:
                path=[]
                current=start
                next_idx=first
                visited=set()
                cumulative=0
                end_boundary=None
                valid=True
                while True:
                    if next_idx in visited:
                        reasons["road_loop"]+=1;valid=False;break
                    visited.add(next_idx)
                    edge=edges[next_idx]
                    at_start=(edge["a"]==current)
                    if not at_start and edge["b"]!=current:
                        reasons["disconnected_edge"]+=1;valid=False;break
                    points=edge["coords"] if at_start else list(reversed(edge["coords"]))
                    if path and metres(path[-1],points[0])>5:
                        reasons["broken_geometry"]+=1;valid=False;break
                    path.extend(points if not path else points[1:])
                    cumulative+=sum(metres(a,b) for a,b in zip(points,points[1:]))
                    if cumulative>2500 or len(path)>500:
                        reasons["unbounded_chain"]+=1;valid=False;break
                    nxt=edge["b"] if at_start else edge["a"]
                    cross,err=crossing(street,nxt)
                    if err:
                        reasons[err]+=1;valid=False;break
                    if cross:
                        end_boundary=cross
                        break
                    onward=[i for i in nodes[nxt] if edges[i]["name"]==street and i !=next_idx]
                    if len(onward)!=1:
                        # 0 may be a cul-de-sac, but not verified without a
                        # complete buffer graph. Flag for manual inspection.
                        reasons["deadend_or_missing_connection" if not onward else "road_branch"]+=1
                        valid=False;break
                    current=nxt
                    next_idx=onward[0]
                if not valid or not end_boundary or from_name==end_boundary or len(path)<2:continue
                if not within(path[0]) or not within(path[-1]):
                    reasons["edge_of_download_bbox"]+=1;continue
                id_parts=sorted(visited)
                key=(street,tuple(id_parts))
                if key in emitted:continue
                emitted.add(key)
                candidates.append({
                  "type":"Feature",
                  "geometry":{"type":"LineString","coordinates":[list(p) for p in path]},
                  "properties":{
                     "roadSegmentId":"vicmap-"+ "-".join(edges[i]["id"] for i in id_parts),
                     "street":street,"from":from_name,"to":end_boundary,
                     "suburbs":sorted({norm(edges[i]["attributes"].get(side))
                           for i in visited for side in ["left_locality","right_locality"]
                           if norm(edges[i]["attributes"].get(side))}),
                     "boundaryEndpointsVerified":False,
                     "reviewState":"TOPOLOGY_CANDIDATE_REQUIRES_INDEPENDENT_VALIDATION",
                     "vicmapPFIs":[edges[i]["id"] for i in id_parts],
                     "possibleSide":False
                  }
                })
    return {"type":"FeatureCollection","features":candidates}, {
        "rawRoadEdges":len(edges),
        "reviewCandidates":len(candidates),
        "sourceRejections":dict(rejected),
        "boundaryAmbiguities":dict(reasons),
        "productionApproved":False
    }

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--input",required=True)
    a.add_argument("--output",required=True)
    a.add_argument("--report",required=True)
    a.add_argument("--bbox",nargs=4,type=float)
    args=a.parse_args()
    doc=json.loads(Path(args.input).read_text())
    result,report=derive_candidates(doc,args.bbox)
    Path(args.output).write_text(json.dumps(result,separators=(",",":"))+"\n")
    Path(args.report).write_text(json.dumps(report,indent=2)+"\n")
    print("VICMAP TOPOLOGY REVIEW",json.dumps(report))
if __name__=="__main__":
    main()
