"""Verify 32 published Footscray segments against original official source and LGA.

Run with --source/--manifest/--candidates/--boundary/--boundary-manifest
inside the official Vicmap acquisition workflow. Fail closed on any source
snapshot change, name mismatch, geometry change, geometry ambiguity, or
published pack drift. No GPS observation/field approval is implied.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from scripts.audit_municipal_candidates import audit, validate_boundary, read_json, metres
from scripts.build_municipal_road_pack import sides_for

ROAD_SHA = "260d28ebcaadea2a5681c85c4245665ee44b8b0d3b1caa91c4bba99887728649"
LGA_SHA = "d56a8917174c3e1752099fbdb9fba77780d274f43bfb03fcd3267d40bce1b5fb"
GEO = Path(__file__).resolve().parents[1] / 'data/reviewed/maribyrnong-footscray-phase3-20261015.geojson'
PACK = Path(__file__).resolve().parents[1] / 'municipal-road-phase3.js'


def pack_segments():
    raw = PACK.read_text(encoding='utf-8')
    match = re.search(r'const additional=(\[.*?\]);', raw)
    if not match:
        raise ValueError('Versioned browser pack has no auditable JSON segment array')
    return json.loads(match.group(1))


def validate_static():
    features = read_json(GEO)['features']
    rows = pack_segments()
    if len(features) != 32 or len(rows) != 32:
        raise ValueError('Expected exactly 32 frozen published source-verified features')
    encountered = set()
    for feature, row in zip(features, rows):
        p = feature['properties']
        geom = feature['geometry']
        identifier = p['roadSegmentId']
        if identifier in encountered:
            raise ValueError('Duplicate published official road PFI')
        encountered.add(identifier)
        if not (p['boundaryEndpointsVerified'] and p['sourceSha256'] == ROAD_SHA
                and p['councilBoundarySha256'] == LGA_SHA
                and p['reviewState'] == 'OFFICIAL_TOPOLOGY_VALIDATED_HANDSET_QA_PENDING'
                and p['suburbs'] == ['FOOTSCRAY']
                and geom['type'] == 'LineString' and len(geom['coordinates']) == 2):
            raise ValueError('Invalid source identity, boundary evidence or review status')
        a, b = geom['coordinates']
        expected_id = 'maribyrnong:' + identifier + ':0'
        if (row['id'] != expected_id or row['street'] != p['street']
                or row['from'] != p['from'] or row['to'] != p['to']
                or row['a'] != list(reversed(a)) or row['b'] != list(reversed(b))
                or row['suburbs'] != ['FOOTSCRAY'] or row['postcode'] != ''
                or not row['startBoundary'] or not row['endBoundary']):
            raise ValueError('Published JS is inconsistent with reviewed official GeoJSON')
        plus, minus = sides_for(row['a'], row['b'])
        if (row['positive'], row['negative']) != (plus, minus):
            raise ValueError('Cardinal sides deviate from reviewed straight-road axis')
        attribution = row['attribution']
        if (attribution.get('roadsSha256'), attribution.get('councilBoundarySha256')) != (ROAD_SHA, LGA_SHA):
            raise ValueError('Published provenance diverges from original official source')
        if attribution.get('licence') != 'CC BY 4.0':
            raise ValueError('State Vicmap attribution/licence missing')
    return features


def validate_source(source, candidates, boundary, manifest, boundary_manifest):
    reviewed = validate_static()
    if manifest.get('sha256') != ROAD_SHA:
        raise ValueError('Original TR_ROAD source version changed; repeat source review')
    if boundary_manifest.get('sha256') != LGA_SHA:
        raise ValueError('Official municipality boundary version changed; repeat polygon review')
    _, verified, _ = audit(source, candidates, boundary, manifest['bboxWGS84'])
    keyed = {f['properties']['roadSegmentId']: f for f in verified['features']}
    for f in reviewed:
        p = f['properties']
        v = keyed.get(p['roadSegmentId'])
        if v is None:
            raise ValueError('Published road not independently audit-eligible: ' + p['roadSegmentId'])
        candidate = v['properties']
        if any(p[k] != candidate[k] for k in ('street', 'from', 'to', 'suburbs')):
            raise ValueError('Published road intersection/locality diverges from official audit')
        if f['geometry'] != v['geometry']:
            raise ValueError('Published geometry differs from official TR_ROAD snapshot')
        if p['vicmapPFI'] != int(candidate['vicmapPFIs'][0]) or len(candidate['vicmapPFIs']) != 1:
            raise ValueError('Published block must refer to exactly one PFI')
        a, b = f['geometry']['coordinates']
        dist = math.hypot((a[1] - b[1]) * 111000, (a[0] - b[0]) * 88000)
        mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
        origin = [144.90335, -37.80205]
        if not 45 <= dist <= 220 or metres(mid, origin) > 650:
            raise ValueError('Published block outside conservative reviewed corridor or length gate')
    return {'releasedSourceVerified': len(reviewed), 'independentlyStaged': len(keyed),
            'sourceSha256': ROAD_SHA, 'councilPolygonSha256': LGA_SHA,
            'handsetFieldQaComplete': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'manifest', 'candidates', 'boundary', 'boundary-manifest'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    src_bytes = Path(args.source).read_bytes()
    boundary_bytes = Path(args.boundary).read_bytes()
    manifest = read_json(args.manifest)
    b_manifest = read_json(args.boundary_manifest)
    if hashlib.sha256(src_bytes).hexdigest() != ROAD_SHA:
        raise ValueError('TR_ROAD source original SHA256 mismatch')
    if hashlib.sha256(boundary_bytes).hexdigest() != LGA_SHA:
        raise ValueError('Official LGA polygon original SHA256 mismatch')
    boundary = validate_boundary(json.loads(boundary_bytes), b_manifest, boundary_bytes)
    result = validate_source(json.loads(src_bytes), read_json(args.candidates),
                             boundary, manifest, b_manifest)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
