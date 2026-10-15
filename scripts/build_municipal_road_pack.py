#!/usr/bin/env python3
"""Build GeoCapture municipal street packs from VERIFIED WGS84 road segments.

Input is GeoJSON FeatureCollection whose features have LineString geometries and:
  street, from, to, boundaryEndpointsVerified=true,
  roadSegmentId (stable), suburb or suburbs, postcode (optional),
  positiveSide and negativeSide (both optional).
'from' and 'to' must refer to the real bordering intersection or DEAD END.
Missing/uncertain boundaries are NOT inferred from OSM way splits.
No GPS coordinates, operator records or payment identifiers are processed.

Usage:
 python scripts/build_municipal_road_pack.py --input reviewed.geojson \\
   --output municipal-road-pack.js --jurisdiction maribyrnong \\
   --source "Reviewed Vicmap Transport + intersection audit" \\
   --licence "CC BY 4.0" --source-url "https://..."
The build must be reviewed and its source data retained before deployment.
"""
import argparse
import json
import math
import pathlib
import sys

CARDINAL = {"NORTH", "SOUTH", "EAST", "WEST"}


def clean(value):
    return str(value or "").strip().upper()


def sides_for(a, b):
    """Infer a cardinal side ONLY if the segment is clearly NS or EW."""
    dy = (b[0] - a[0]) * 111000
    dx = (b[1] - a[1]) * 111000 * math.cos(math.radians((a[0] + b[0]) / 2))
    if abs(dy) > abs(dx) * 2 and abs(dy) > 0.1:
        return ("EAST", "WEST") if dy > 0 else ("WEST", "EAST")
    if abs(dx) > abs(dy) * 2 and abs(dx) > 0.1:
        return ("SOUTH", "NORTH") if dx > 0 else ("NORTH", "SOUTH")
    return ("", "")  # Diagonal roads require field-verified side.


def build(doc, jurisdiction, source, licence, source_url):
    if doc.get("type") != "FeatureCollection":
        raise ValueError("Input must be GeoJSON FeatureCollection")
    crs = doc.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
    if crs not in {"EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84", "CRS84"}:
        raise ValueError("Reproject geographic source to WGS84 lon/lat before import")
    segments = []
    rejected = []
    seen = set()
    for idx, feature in enumerate(doc.get("features", [])):
        p = feature.get("properties") or {}
        g = feature.get("geometry") or {}
        name, a_name, b_name = (clean(p.get(k)) for k in ("street", "from", "to"))
        identifier = str(p.get("roadSegmentId", "")).strip()
        coords = g.get("coordinates", [])
        reason = None
        if not (identifier and name and a_name and b_name and a_name != b_name):
            reason = "missing stable ID or audited street/boundaries"
        elif p.get("boundaryEndpointsVerified") is not True:
            reason = "unverified endpoint/intersection topology"
        elif g.get("type") != "LineString" or len(coords) < 2:
            reason = "not a two-point-or-longer LineString"
        elif not all(isinstance(pt, list) and len(pt) >= 2 and
                     all(isinstance(v, (float, int)) and math.isfinite(v) for v in pt[:2]) and
                     -180 <= pt[0] <= 180 and -90 <= pt[1] <= 90 for pt in coords):
            reason = "invalid WGS84 coordinate"
        if reason:
            rejected.append((idx, reason))
            continue
        if identifier in seen:
            rejected.append((idx, "duplicate roadSegmentId"))
            continue
        seen.add(identifier)
        suburb = p.get("suburbs", p.get("suburb", []))
        if isinstance(suburb, str):
            suburb = [suburb]
        postcode = str(p.get("postcode") or "")
        explicit_pos, explicit_neg = clean(p.get("positiveSide")), clean(p.get("negativeSide"))
        if (explicit_pos or explicit_neg) and not ({explicit_pos, explicit_neg} <= CARDINAL):
            rejected.append((idx, "incomplete/invalid explicit cardinal side metadata"))
            continue
        for edge, (start, end) in enumerate(zip(coords, coords[1:])):
            a = [float(start[1]), float(start[0])]
            b = [float(end[1]), float(end[0])]
            if math.hypot((b[0] - a[0]) * 111000,
                          (b[1] - a[1]) * 111000 * math.cos(math.radians(a[0]))) < 0.25:
                continue
            positive, negative = (explicit_pos, explicit_neg) if explicit_pos else sides_for(a, b)
            segments.append({
                "id": f"{jurisdiction}:{identifier}:{edge}",
                "street": name, "from": a_name, "to": b_name,
                "a": a, "b": b, "positive": positive, "negative": negative,
                "suburbs": [clean(s) for s in suburb if str(s).strip()],
                "postcode": postcode,
                "startBoundary": edge == 0,
                "endBoundary": edge == len(coords) - 2,
                "attribution": {"source": source, "licence": licence, "url": source_url,
                                "jurisdiction": jurisdiction}
            })
    return segments, rejected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("input", "output", "jurisdiction", "source", "licence", "source-url"):
        p.add_argument("--" + key, required=True)
    args = p.parse_args()
    doc = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    rows, skipped = build(doc, args.jurisdiction, args.source, args.licence, args.source_url)
    if not rows:
        raise SystemExit("No verified road segments; refusing to publish an empty pack")
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    script = (
        "/* Generated from reviewed municipal GeoJSON; preserve attribution. */\n"
        "(function(root){ 'use strict';\n"
        "const before=root.GeoCaptureRoadData;\n"
        "if(!before) throw new Error('Load local-road-data.js first');\n"
        "root.GeoCaptureRoadData=Object.freeze({...before,"
        "version:before.version+" + json.dumps("+" + args.jurisdiction) + ","
        "segments:before.segments.concat(" + payload + ")});\n"
        "})(typeof globalThis==='object'?globalThis:this);\n"
    )
    pathlib.Path(args.output).write_text(script, encoding="utf-8")
    print(f"Verified road-geometry edges: {len(rows)}; rejected features: {len(skipped)}", file=sys.stderr)
    for idx, reason in skipped[:25]:
        print(f"  feature {idx}: {reason}", file=sys.stderr)
    if skipped:
        print("ATTENTION: review rejected feature list before deployment", file=sys.stderr)


if __name__ == "__main__":
    main()
