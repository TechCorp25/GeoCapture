#!/usr/bin/env python3
"""Read-only diagnostics for one named Vicmap road, without exposing capture GPS."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from scripts.review_vicmap_topology import road_graph, metres

def inspect(data, name):
    edges,nodes,corrupt,rejected=road_graph(data)
    matches=[e for e in edges if e["name"]==name]
    rows=[]
    for e in matches:
        rec={"pfi":e["id"],
             "endpoints":[],"coordCount":len(e["coords"])}
        for node,at in ((e["a"],e["coords"][0]),(e["b"],e["coords"][-1])):
            neighbours=sorted({edges[i]["name"] or "<UNNAMED>"
                              for i in nodes[node] if edges[i]["id"]!=e["id"]})
            rec["endpoints"].append({"node":node,"location":list(at),"connectedNames":neighbours,
                "degree":len(nodes[node]),"nodeInconsistent":node in corrupt})
        rows.append(rec)
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--street",default="TALBOT STREET")
    a=p.parse_args()
    data=json.loads(Path(a.input).read_text())
    items=inspect(data,a.street.upper())
    print("STREET_REVIEW_BEGIN",a.street.upper(),"count",len(items))
    for item in items[:40]:print(json.dumps(item))
    print("STREET_REVIEW_END")
if __name__=="__main__":main()
