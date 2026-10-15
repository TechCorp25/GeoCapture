#!/usr/bin/env python3
"""Fetch a bounded, reproducible snapshot of official Vicmap Transport TR_ROAD.

This tool executes at build time only. GeoCapture devices never contact Vicmap.
ArcGIS endpoint and fields independently checked against official service docs.
All raw records remain REVIEW CANDIDATES until topology and field QA complete.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

LAYER = "https://vicmap.land.vic.gov.au/agsgis/rest/services/vicmap/Vicmap_Transport/MapServer/1/query"
ATTRS = "id,ufi,pfi,ezi_road_name,road_name,road_type,left_locality,right_locality,from_ufi,to_ufi,feature_type_code,class_code,structure_name,road_status,vehicular_access"
# Wide Footscray staging bounds, not an authoritative LGA polygon.
DEFAULT_BBOX = (144.87, -37.835, 144.945, -37.785)
PAGE_SIZE = 500
AGENT = "GeoCapture engineering road-index builder (offline source acquisition; contact via project repository)"

def fetch_page(params, tries=3):
    url = LAYER + "?" + urllib.parse.urlencode(params, safe=",")
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=35) as response:
                data = response.read(18_000_000 + 1)
                if len(data) > 18_000_000:
                    raise ValueError("Unexpectedly large ArcGIS response")
                doc = json.loads(data)
                if isinstance(doc, dict) and doc.get("error"):
                    raise ValueError("Vicmap ArcGIS query error: " + str(doc["error"]))
                return doc
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            if attempt == tries - 1:
                raise RuntimeError("Official Vicmap service unavailable") from error
            time.sleep(2 ** attempt)

def collect(bbox, max_features=12000):
    min_x, min_y, max_x, max_y = bbox
    if not (143 < min_x < max_x < 146 and -39 < min_y < max_y < -36):
        raise ValueError("Expected bounded Melbourne-area WGS84 bbox")
    base = {
        "where": "1=1", "geometry": ",".join(map(str, bbox)),
        "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ATTRS, "returnGeometry": "true",
        "outSR": 4326, "f": "geojson",
    }
    features_by_id = {}
    offset = 0
    while True:
        doc = fetch_page({**base, "resultOffset": offset, "resultRecordCount": PAGE_SIZE,
                          "orderByFields": "id ASC"})
        if doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
            raise ValueError("Vicmap did not return a GeoJSON FeatureCollection")
        batch = doc["features"]
        if not batch:
            break
        for item in batch:
            p = item.get("properties") or {}
            identifier = p.get("pfi") or p.get("ufi") or p.get("id") or item.get("id")
            if identifier is not None:
                features_by_id[str(identifier)] = item
        offset += len(batch)
        if len(features_by_id) > max_features:
            raise ValueError("Road-snapshot extent too broad; reduce bbox and retry")
        if len(batch) < PAGE_SIZE and not doc.get("exceededTransferLimit"):
            break
        if offset > max_features + PAGE_SIZE:
            raise ValueError("Pagination exhausted capacity; refusing truncated snapshot")
    if not features_by_id:
        raise ValueError("No features returned; refusing to publish empty snapshot")
    records = sorted(features_by_id.values(), key=lambda x: str(
        (x.get("properties") or {}).get("pfi") or x.get("id") or ""))
    return {"type": "FeatureCollection", "features": records}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--bbox", nargs=4, type=float, default=list(DEFAULT_BBOX))
    args = parser.parse_args()
    bbox = tuple(args.bbox)
    doc = collect(bbox)
    dest = pathlib.Path(args.output); dest.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(doc, separators=(",", ":"), ensure_ascii=False)+"\n").encode("utf-8")
    dest.write_bytes(encoded)
    manifest = {
        "source": "Vicmap Transport TR_ROAD (Department of Transport and Planning, Victoria)",
        "serviceUrl": LAYER, "licence": "CC BY 4.0",
        "licenceUrl": "https://creativecommons.org/licenses/by/4.0/",
        "retrievedUTC": dt.datetime.now(dt.timezone.utc).isoformat(),
        "bboxWGS84": bbox, "featureCount": len(doc["features"]),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "reviewStatus": "UNVERIFIED_CANDIDATE_NOT_FOR_PRODUCTION",
        "note": "Bbox is a Footscray study area, not a legally accurate council boundary.",
    }
    pathlib.Path(args.manifest).write_text(json.dumps(manifest, indent=2)+"\n")
    print("VICMAP:",json.dumps(manifest))
if __name__ == "__main__":
    main()
