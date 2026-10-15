"""Independent GeoCapture Vicmap topology and LGA release-gate tests."""
import hashlib
import json
import unittest
from scripts.audit_municipal_candidates import audit, validate_boundary
from scripts.fetch_vicmap_lga import acquire


def road(pfi, name, coords, fr, to, **kw):
    return {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': coords},
            'properties': {'pfi': pfi, 'ezi_road_name': name, 'from_ufi': fr, 'to_ufi': to,
                           'road_status': 'O', 'vehicular_access': '1', 'class_code': 5,
                           'feature_type_code': 'road', 'left_locality': 'FOOTSCRAY',
                           'right_locality': 'FOOTSCRAY', **kw}}


A = [144.900, -37.800]
B = [144.902, -37.800]
POLYGON = {'type': 'Polygon', 'coordinates': [[[144.89, -37.81], [144.91, -37.81],
                                            [144.91, -37.79], [144.89, -37.79],
                                            [144.89, -37.81]]]}


def fixture():
    source = {'type': 'FeatureCollection', 'features': [
        road(1, 'TEST STREET', [A, B], 10, 20),
        road(2, 'CROSS ROAD', [[144.9, -37.801], A], 30, 10),
        road(3, 'CROSS ROAD', [A, [144.9, -37.799]], 10, 31),
        road(4, 'OTHER ROAD', [[144.902, -37.801], B], 40, 20),
        road(5, 'OTHER ROAD', [B, [144.902, -37.799]], 20, 41)]}
    candidate = {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': [A, B]},
                 'properties': {'roadSegmentId': 'vicmap-1', 'street': 'TEST STREET',
                                'from': 'CROSS ROAD', 'to': 'OTHER ROAD',
                                'suburbs': ['FOOTSCRAY'], 'vicmapPFIs': ['1'],
                                'boundaryEndpointsVerified': False}}
    return source, {'type': 'FeatureCollection', 'features': [candidate]}


class IndependentMunicipalAuditTests(unittest.TestCase):
    def test_proven_network_junctions_and_polygon_stage_but_do_not_publish(self):
        source, candidates = fixture()
        rows, staged, report = audit(source, candidates, POLYGON)
        self.assertEqual(report['eligibleForPackageReview'], 1)
        self.assertEqual(report['published'], 0)
        self.assertEqual(rows[0]['status'], 'ELIGIBLE')
        self.assertTrue(staged['features'][0]['properties']['boundaryEndpointsVerified'])
        self.assertNotIn('postcode', staged['features'][0]['properties'])

    def test_missing_boundary_does_not_certify_candidate(self):
        source, candidates = fixture()
        rows, staged, report = audit(source, candidates)
        self.assertEqual(report['pending'], 1)
        self.assertEqual(rows[0]['reason'], 'official_lga_boundary_not_loaded')
        self.assertEqual(staged['features'], [])

    def test_grade_separation_disallows_staging(self):
        source, candidates = fixture()
        source['features'][1]['properties']['feature_type_code'] = 'bridge'
        rows, _, report = audit(source, candidates, POLYGON)
        self.assertEqual(report['pending'], 1)
        self.assertEqual(rows[0]['reason'], 'structure_at_junction')

    def test_conflicting_cross_name_and_unknown_source_pfi(self):
        source, candidates = fixture()
        candidates['features'][0]['properties']['to'] = 'WRONG ROAD'
        rows, _, _ = audit(source, candidates, POLYGON)
        self.assertEqual(rows[0]['reason'], 'source_intersection_not_unique')
        candidates['features'][0]['properties']['vicmapPFIs'] = ['8888']
        rows, _, _ = audit(source, candidates, POLYGON)
        self.assertEqual(rows[0]['status'], 'REJECT')

    def test_outside_lga_cannot_be_staged(self):
        source, candidates = fixture()
        outside = {'type': 'Polygon', 'coordinates': [[[145, -37.9], [146, -37.9],
                   [146, -37.8], [145, -37.8], [145, -37.9]]]}
        rows, _, _ = audit(source, candidates, outside)
        self.assertEqual(rows[0]['reason'], 'crosses_or_outside_municipal_boundary')

    def test_boundary_manifest_checksum_enforced(self):
        doc = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'LGA_NAME': 'MARIBYRNONG'},
             'geometry': POLYGON}]}
        raw = (json.dumps(doc) + '\n').encode()
        manifest = {'sha256': hashlib.sha256(raw).hexdigest(),
                    'serviceUrl': 'https://vicmap.land.vic.gov.au/agsgis/rest/services/vicmap/Vicmap_Admin/MapServer/9',
                    'licence': 'CC BY 4.0'}
        self.assertEqual(validate_boundary(doc, manifest, raw), POLYGON)
        with self.assertRaises(ValueError):
            validate_boundary(doc, {**manifest, 'sha256': 'tampered'}, raw)

    def test_official_fetch_fails_closed(self):
        doc = {'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'LGA_NAME': 'MARIBYRNONG'},
             'geometry': POLYGON}]}
        payload, manifest = acquire(fetch=lambda url: json.dumps(doc).encode())
        self.assertEqual(manifest['sha256'], hashlib.sha256(payload).hexdigest())
        with self.assertRaises(ValueError):
            acquire(fetch=lambda url: b'{"features":[]}')


if __name__ == '__main__':
    unittest.main()
