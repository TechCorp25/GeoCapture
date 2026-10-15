"""Phase 4 whole-municipality collection and complete feature-ledger safeguards."""
import copy
import unittest
from unittest.mock import patch

from scripts.fetch_vicmap_roads import collect_municipality, polygon_bounds
from scripts.maribyrnong_inventory import line_membership, reconcile

RING = [[144.89, -37.82], [144.92, -37.82], [144.92, -37.79],
        [144.89, -37.79], [144.89, -37.82]]
BOUNDARY = {"type": "Polygon", "coordinates": [RING]}


def feature(pfi, geometry=None, name="TEST STREET"):
    return {"type": "Feature", "geometry": {"type": "LineString",
            "coordinates": geometry or [[144.900, -37.800], [144.902, -37.800]]},
            "properties": {"pfi": pfi, "id": pfi + 1000,
                "ezi_road_name": name, "feature_type_code": "road",
                "class_code": 5, "road_status": "O", "vehicular_access": "1",
                "left_locality": "FOOTSCRAY", "right_locality": "FOOTSCRAY",
                "from_ufi": pfi * 2, "to_ufi": pfi * 2 + 1}}


class WholeMunicipalityTests(unittest.TestCase):
    def test_polygon_extent_is_generated_from_actual_council_geometry(self):
        box = polygon_bounds(BOUNDARY, 600)
        self.assertLess(box[0], .89 + 144)
        self.assertGreater(box[2], 144.92)
        self.assertLess(box[1], -37.82)
        self.assertGreater(box[3], -37.79)
        with self.assertRaisesRegex(ValueError, "buffer"):
            polygon_bounds(BOUNDARY, 0)

    def test_interior_crossing_and_outside_are_distinct(self):
        self.assertEqual(line_membership([[144.900, -37.8], [144.901, -37.8]], BOUNDARY), "INSIDE")
        self.assertEqual(line_membership([[144.880, -37.8], [144.900, -37.8]], BOUNDARY), "CROSSING")
        self.assertEqual(line_membership([[144.880, -37.8], [144.885, -37.8]], BOUNDARY), "OUTSIDE")
        self.assertEqual(line_membership([[144.880, -37.8], [144.93, -37.8]], BOUNDARY), "CROSSING")

    def test_hole_is_not_mistaken_for_council_membership(self):
        geom = copy.deepcopy(BOUNDARY)
        geom["coordinates"].append([[144.899, -37.801], [144.903, -37.801],
                                    [144.903, -37.799], [144.899, -37.799],
                                    [144.899, -37.801]])
        self.assertEqual(line_membership([[144.9, -37.8], [144.901, -37.8]], geom), "OUTSIDE")

    def test_snapshot_id_inventory_mismatch_fails_closed(self):
        response = {"objectIds": [1001, 1002], "objectIdFieldName": "id"}
        with patch("scripts.fetch_vicmap_roads.fetch_page", return_value=response), patch(
            "scripts.fetch_vicmap_roads.collect",
            return_value={"type": "FeatureCollection", "features": [feature(1)]}):
            with self.assertRaisesRegex(ValueError, "pagination"):
                collect_municipality(BOUNDARY)

    def test_snapshot_id_set_and_snapshot_feature_count_match(self):
        response = {"objectIds": [1001], "objectIdFieldName": "id"}
        with patch("scripts.fetch_vicmap_roads.fetch_page", side_effect=[response, response]), patch(
            "scripts.fetch_vicmap_roads.collect",
            return_value={"type": "FeatureCollection", "features": [feature(1)]}):
            result, meta = collect_municipality(BOUNDARY)
        self.assertEqual(meta["officialObjectIdCount"], 1)
        self.assertTrue(meta["paginationVerified"])
        self.assertEqual(len(result["features"]), 1)

    def test_every_feature_classified_without_publishing_candidates(self):
        docs = [feature(1), feature(2, [[144.88,-37.8], [144.901,-37.8]]),
                feature(3, [[144.88,-37.8], [144.885,-37.8]]),
                feature(4, name="UNNAMED")]
        source = {"type":"FeatureCollection","features":docs}
        cand = {"features":[{"properties":{"roadSegmentId":"vicmap-1",
                                "vicmapPFIs":["1"],"street":"TEST STREET",
                                "from":"A ROAD","to":"B ROAD"}}]}
        decisions = [{"roadSegmentId":"vicmap-1","status":"ELIGIBLE",
                      "reason":"independently_confirmed_source_ufi_geometry_and_lga"}]
        reviewed = [{"properties":{"vicmapPFI":1,"boundaryEndpointsVerified":True},
                     "geometry":copy.deepcopy(docs[0]["geometry"])}]
        roads, road_blocks, report = reconcile(source, BOUNDARY, cand,
                                               decisions, reviewed, "a", "b")
        self.assertEqual(len(roads),4)
        self.assertEqual(len(road_blocks),1)
        self.assertEqual([r["status"] for r in sorted(roads,key=lambda x:x["sourcePFI"])],
                         ["VERIFIED","PENDING_REVIEW","OUT_OF_SCOPE","UNSUPPORTED"])
        self.assertEqual(report["previouslyPublishedGeometryMatched"],1)
        self.assertFalse(report["completeCoverageClaim"])

    def test_changed_published_geometry_cannot_remain_verified(self):
        source = {"type":"FeatureCollection","features":[feature(1)]}
        f = feature(1, [[144.9,-37.8],[144.903,-37.8]])
        f["properties"]["vicmapPFI"] = 1
        f["properties"]["boundaryEndpointsVerified"] = True
        rows, _, _ = reconcile(source, BOUNDARY, {"features":[]}, [], [f], "a", "b")
        self.assertEqual(rows[0]["status"],"PENDING_REVIEW")
        self.assertFalse(rows[0]["referenceGeometryMatchesCurrentSource"])


if __name__ == "__main__":
    unittest.main()
