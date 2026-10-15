import unittest
from unittest.mock import patch

from scripts.fetch_vicmap_roads import collect
from scripts.review_vicmap_topology import derive_candidates

def line(pfi, name, pts, a, b, **extra):
    return {
        "type":"Feature",
        "geometry":{"type":"LineString","coordinates":pts},
        "properties":{"pfi":pfi,"ezi_road_name":name,"from_ufi":a,"to_ufi":b,
                      "left_locality":"Footscray","right_locality":"Footscray",**extra}
    }
def network():
    # Named intersections A and C, with one internal same-name road split B.
    return {"type":"FeatureCollection","features":[
        line(1,"TALBOT STREET",[[144.9,-37.8],[144.9,-37.801]],101,102),
        line(2,"TALBOT STREET",[[144.9,-37.801],[144.9,-37.802]],102,103),
        line(3,"COWPER STREET",[[144.899,-37.8],[144.9,-37.8]],104,101),
        line(4,"COWPER STREET",[[144.9,-37.8],[144.901,-37.8]],101,105),
        line(5,"HOOK ROAD",[[144.899,-37.802],[144.9,-37.802]],106,103),
        line(6,"HOOK ROAD",[[144.9,-37.802],[144.901,-37.802]],103,107),
    ]}

class VicmapTopologyTests(unittest.TestCase):
    def test_connected_named_intersections_produce_review_candidates_not_live(self):
        candidates, report = derive_candidates(network())
        matched = [x for x in candidates["features"] if x["properties"]["street"]=="TALBOT STREET"]
        self.assertEqual(report["productionApproved"],False)
        self.assertEqual(len(matched),1)
        self.assertEqual({matched[0]["properties"]["from"],matched[0]["properties"]["to"]},
                         {"COWPER STREET","HOOK ROAD"})
        self.assertEqual(len(matched[0]["geometry"]["coordinates"]),3)
        self.assertIs(matched[0]["properties"]["boundaryEndpointsVerified"],False)
    def test_branch_ambiguity_rejected(self):
        d=network()
        d["features"].append(line(7,"BRANCH AVENUE",[[144.9,-37.801],[144.901,-37.801]],102,108))
        d["features"].append(line(8,"OTHER ROAD",[[144.9,-37.801],[144.899,-37.801]],102,109))
        # Two distinct crossing roads at the same junction are explicitly ambiguous.
        candidates,_=derive_candidates(d)
        self.assertFalse(any(x["properties"]["street"]=="TALBOT STREET" for x in candidates["features"]))
    def test_road_crossing_without_shared_node_not_an_intersection(self):
        d=network()
        d["features"][4]["properties"]["to_ufi"]=999
        d["features"][5]["properties"]["from_ufi"]=999
        # C endpoint no longer connects Hook Road, so no verified other end.
        c,_=derive_candidates(d)
        self.assertFalse(any(x["properties"]["street"]=="TALBOT STREET" for x in c["features"]))
    def test_pagination_and_deduplication_are_explicit(self):
        p={"type":"FeatureCollection","features":network()["features"]}
        with patch("scripts.fetch_vicmap_roads.fetch_page",side_effect=[p,{"type":"FeatureCollection","features":[]}]) as fetch:
            r=collect((144.87,-37.835,144.945,-37.785))
            self.assertEqual(len(r["features"]),6)
            self.assertIn("resultOffset",fetch.call_args.args[0])
    def test_no_truncated_silent_empty_results(self):
        with patch("scripts.fetch_vicmap_roads.fetch_page",return_value={"type":"FeatureCollection","features":[]}):
            with self.assertRaisesRegex(ValueError,"No features"):
                collect((144.87,-37.835,144.945,-37.785))

if __name__=="__main__":
    unittest.main()
