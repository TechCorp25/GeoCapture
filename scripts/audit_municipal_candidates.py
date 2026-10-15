#!/usr/bin/env python3
"""Independent, fail-closed Vicmap topology audit. No automatic deployment.

Compare original TR_ROAD feature geometry and UFI connectivity against review
candidates, then require an authoritative Vicmap Admin council polygon.
Every candidate receives a disposition. Staged eligible results still need
a separate reviewed package build and release approval.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

BOUNDS = (144.87, -37.835, 144.945, -37.785)
VALID_CLASSES = {3, 4, 5}
MIN_LENGTH_METRES = 12


def norm(value):
    return ' '.join(str(value or '').upper().split())


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111000 * math.cos(math.radians((a[1] + b[1]) / 2)),
                      (a[1] - b[1]) * 111000)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rings_contain(point, polygon):
    def within(ring):
        x, y = point
        inside = False
        for a, b in zip(ring, ring[1:] + ring[:1]):
            if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
        return inside
    return bool(polygon and within(polygon[0]) and not any(within(r) for r in polygon[1:]))


def in_boundary(point, geometry):
    if geometry['type'] == 'Polygon':
        return rings_contain(point, geometry['coordinates'])
    if geometry['type'] == 'MultiPolygon':
        return any(rings_contain(point, polygon) for polygon in geometry['coordinates'])
    return False


def validate_boundary(boundary, manifest, raw):
    if hashlib.sha256(raw).hexdigest() != manifest.get('sha256'):
        raise ValueError('Official council polygon SHA256 mismatch')
    features = boundary.get('features') or []
    if boundary.get('type') != 'FeatureCollection' or len(features) != 1:
        raise ValueError('Require exactly one official council polygon')
    feature = features[0]
    props = feature.get('properties') or {}
    allowed = {'MARIBYRNONG', 'MARIBYRNONG (C)', 'CITY OF MARIBYRNONG', 'MARIBYRNONG CITY COUNCIL'}
    if not any(norm(v) in allowed for k, v in props.items() if 'name' in k.lower()):
        raise ValueError('LGA name does not identify Maribyrnong')
    geometry = feature.get('geometry') or {}
    if geometry.get('type') not in ('Polygon', 'MultiPolygon'):
        raise ValueError('Expected polygon or multipolygon')
    if 'Vicmap_Admin/MapServer/9' not in manifest.get('serviceUrl', ''):
        raise ValueError('Expected official Vicmap Admin LGA layer 9')
    if manifest.get('licence') != 'CC BY 4.0':
        raise ValueError('Official council boundary licence missing')
    return geometry


def graph_features(source):
    by_pfi = {}
    nodes = defaultdict(list)
    for feature in source.get('features', []):
        props = feature.get('properties') or {}
        pfi = props.get('pfi')
        coords = (feature.get('geometry') or {}).get('coordinates') or []
        if pfi is None or (feature.get('geometry') or {}).get('type') != 'LineString' or len(coords) < 2:
            continue
        by_pfi[str(pfi)] = feature
        for attr, coordinate in (('from_ufi', coords[0]), ('to_ufi', coords[-1])):
            node = props.get(attr)
            if node not in (None, 0, '0', ''):
                nodes[str(node)].append((feature, coordinate))
    return by_pfi, nodes


def audit_one(candidate, by_pfi, nodes, boundary, bbox):
    props = candidate.get('properties') or {}
    ids = props.get('vicmapPFIs') or []
    coords = (candidate.get('geometry') or {}).get('coordinates') or []
    if not ids or not all(props.get(k) for k in ('roadSegmentId', 'street', 'from', 'to')):
        return 'REJECT', 'missing_identity_or_boundaries'
    if norm(props['from']) == norm(props['to']):
        return 'PENDING', 'repeated_boundary_name_requires_review'
    if props.get('boundaryEndpointsVerified') is True:
        return 'REJECT', 'input_preapproved_without_independent_audit'
    if len(set(ids)) != len(ids) or any(str(i) not in by_pfi for i in ids):
        return 'REJECT', 'missing_or_duplicate_source_pfi'
    if len(coords) < 2 or any(len(p) < 2 or not all(math.isfinite(v) for v in p[:2]) for p in coords):
        return 'REJECT', 'invalid_geometry'
    if sum(metres(a, b) for a, b in zip(coords, coords[1:])) < MIN_LENGTH_METRES:
        return 'PENDING', 'short_block_gps_ambiguity'
    if any(not (bbox[0] + .001 < p[0] < bbox[2] - .001 and
                    bbox[1] + .001 < p[1] < bbox[3] - .001)
           for p in (coords[0], coords[-1])):
        return 'PENDING', 'source_extent_margin'
    street = norm(props['street'])
    localities = set()
    for identifier in ids:
        original = by_pfi[str(identifier)]['properties']
        if (norm(original.get('ezi_road_name')) != street
                or norm(original.get('feature_type_code')) != 'ROAD'
                or norm(original.get('road_status')) != 'O'
                or str(original.get('vehicular_access')) != '1'
                or original.get('structure_name')
                or original.get('class_code') not in VALID_CLASSES):
            return 'PENDING', 'source_road_class_or_access_requires_review'
        if original.get('from_ufi') in (None, 0, '0') or original.get('to_ufi') in (None, 0, '0'):
            return 'PENDING', 'missing_source_network_ufi'
        localities.update(norm(original.get(k)) for k in ('left_locality', 'right_locality')
                          if norm(original.get(k)))
    if set(props.get('suburbs') or []) != localities:
        return 'PENDING', 'candidate_locality_conflict'
    # Reconstruct candidate from official PFI source geometries with UFI continuity.
    unused = {str(i) for i in ids}
    reconstructed = []
    endpoints = []
    current = coords[0]
    last_node = None
    while unused:
        options = []
        for identifier in unused:
            original = by_pfi[identifier]
            line = original['geometry']['coordinates']
            source = original['properties']
            if metres(line[0], current) < 2:
                options.append((identifier, line, str(source['from_ufi']), str(source['to_ufi'])))
            if metres(line[-1], current) < 2:
                options.append((identifier, list(reversed(line)), str(source['to_ufi']), str(source['from_ufi'])))
        if len(options) != 1:
            return 'PENDING', 'ambiguous_or_disconnected_pfi_chain'
        identifier, line, entry, exit_node = options[0]
        if last_node is not None and entry != last_node:
            return 'PENDING', 'same_coordinates_not_connected_ufi'
        if not endpoints:
            endpoints.append(entry)
        reconstructed.extend(line if not reconstructed else line[1:])
        current = line[-1]
        last_node = exit_node
        unused.remove(identifier)
    endpoints.append(last_node)
    if len(reconstructed) != len(coords) or any(metres(a, b) > 2 for a, b in zip(reconstructed, coords)):
        return 'PENDING', 'candidate_geometry_differs_from_source'
    if len(set(endpoints)) != 2 or metres(coords[-1], current) > 2:
        return 'REJECT', 'degenerate_terminal_identity'
    for node, label in zip(endpoints, (props['from'], props['to'])):
        adjacent = nodes.get(node, [])
        expected = coords[0] if node == endpoints[0] else coords[-1]
        if not adjacent or any(metres(coordinate, expected) > 5 for _, coordinate in adjacent):
            return 'PENDING', 'network_ufi_coordinate_inconsistent'
        names = {norm(f['properties'].get('ezi_road_name')) for f, _ in adjacent}
        if 'UNNAMED' in names or '' in names:
            return 'PENDING', 'unnamed_road_at_intersection'
        if names - {street} != {norm(label)}:
            return 'PENDING', 'source_intersection_not_unique'
        if any(f['properties'].get('structure_name') or
               norm(f['properties'].get('feature_type_code')) != 'ROAD' for f, _ in adjacent):
            return 'PENDING', 'structure_at_junction'
    if not boundary:
        return 'PENDING', 'official_lga_boundary_not_loaded'
    if any(not in_boundary(p, boundary) for p in
           (coords[0], coords[len(coords) // 2], coords[-1])):
        return 'PENDING', 'crosses_or_outside_municipal_boundary'
    return 'ELIGIBLE', 'independently_confirmed_source_ufi_geometry_and_lga'


def audit(source, candidates, boundary=None, bbox=BOUNDS):
    by_pfi, nodes = graph_features(source)
    dispositions = []
    verified = []
    counts = Counter()
    for idx, feature in enumerate(candidates.get('features', [])):
        state, reason = audit_one(feature, by_pfi, nodes, boundary, bbox)
        counts[state] += 1
        counts[state + ':' + reason] += 1
        props = feature.get('properties') or {}
        dispositions.append({'candidateIndex': idx, 'roadSegmentId': props.get('roadSegmentId'),
                             'street': props.get('street'), 'status': state, 'reason': reason})
        if state == 'ELIGIBLE':
            output = json.loads(json.dumps(feature))
            output['properties']['boundaryEndpointsVerified'] = True
            output['properties']['reviewState'] = 'SOURCE_AND_LGA_AUDITED_RELEASE_REVIEW_REQUIRED'
            output['properties']['reviewEvidence'] = (
                'Vicmap road UFI/PFI reconstruction, distinct actual junction road names, '
                'Vicmap Admin LGA containment. GPS field validation not performed.')
            output['properties'].pop('possibleSide', None)
            verified.append(output)
    report = {'totalCandidates': len(dispositions), 'eligibleForPackageReview': counts['ELIGIBLE'],
              'pending': counts['PENDING'], 'rejected': counts['REJECT'], 'published': 0,
              'reasonCounts': {k: v for k, v in sorted(counts.items()) if ':' in k},
              'municipalityGeometryVerified': bool(boundary),
              'releaseGate': 'STAGING_ONLY_NO_AUTOMATIC_PUBLICATION'}
    return dispositions, {'type': 'FeatureCollection', 'features': verified}, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'source-manifest', 'candidates', 'dispositions', 'verified', 'report'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--boundary')
    parser.add_argument('--boundary-manifest')
    parser.add_argument('--bbox', nargs=4, type=float, default=list(BOUNDS))
    args = parser.parse_args()
    if bool(args.boundary) != bool(args.boundary_manifest):
        parser.error('--boundary and --boundary-manifest must be provided together')
    source_manifest = read_json(args.source_manifest)
    if hashlib.sha256(Path(args.source).read_bytes()).hexdigest() != source_manifest.get('sha256'):
        raise ValueError('Vicmap road source checksum mismatch')
    if 'Vicmap_Transport/MapServer/1/query' not in source_manifest.get('serviceUrl', ''):
        raise ValueError('Expected official Vicmap Transport road layer')
    boundary = None
    if args.boundary:
        raw = Path(args.boundary).read_bytes()
        boundary = validate_boundary(json.loads(raw), read_json(args.boundary_manifest), raw)
    bbox = args.bbox if args.bbox != list(BOUNDS) else source_manifest.get('bboxWGS84', args.bbox)
    dispositions, verified, report = audit(read_json(args.source), read_json(args.candidates),
                                           boundary, bbox)
    for path, document in ((args.dispositions, dispositions), (args.verified, verified), (args.report, report)):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(document, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
