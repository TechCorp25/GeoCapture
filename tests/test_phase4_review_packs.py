"""Municipal staging packages never auto-publish or duplicate road blocks."""
import unittest
from scripts.stage_municipal_packs import stage


def candidate(identifier, pfi, suburbs=None):
    return {"type":"Feature",
            "geometry":{"type":"LineString","coordinates":[[144.90,-37.80],[144.901,-37.80]]},
            "properties":{"roadSegmentId":identifier,"vicmapPFIs":[pfi],
                          "street":"TEST STREET","from":"ROAD A","to":"ROAD B",
                          "suburbs":suburbs or ["FOOTSCRAY"],
                          "boundaryEndpointsVerified":True}}


def entry(identifier, publication="STAGED_NOT_PUBLISHED", membership="INSIDE"):
    return {"candidateId":identifier,"topologyAuditStatus":"ELIGIBLE",
            "municipalityMembership":membership,"publicationStatus":publication}


class ReviewPackTests(unittest.TestCase):
    def test_one_qualified_candidate_is_staged_not_published(self):
        packs, exceptions, manifest = stage(
            {"features":[candidate("a",1)]},[entry("a")],"roadsha","lgasha")
        self.assertEqual(set(packs),{"footscray"})
        self.assertEqual(manifest["stagedCandidates"],1)
        self.assertEqual(exceptions,[])
        self.assertIn(b"STAGED_OFFLINE_NOT_PUBLISHED",packs["footscray"])
        self.assertNotIn(b"positiveSide",packs["footscray"])

    def test_published_and_outside_stay_excluded(self):
        rows=[candidate("a",1),candidate("b",2)]
        ledger=[entry("a","PUBLISHED_PREVIOUS_PHASE"),entry("b",membership="CROSSING")]
        packs, exceptions, manifest=stage({"features":rows},ledger,"road","lga")
        self.assertEqual(packs,{})
        self.assertEqual(manifest["excludedFromStaging"],2)
        self.assertEqual({x["reason"] for x in exceptions},
                         {"previously_published_do_not_duplicate","not_fully_contained_in_lga"})

    def test_multi_locality_package_does_not_duplicate(self):
        feature=candidate("a",1,["YARRAVILLE","SEDDON"])
        packs, _, _=stage({"features":[feature]},[entry("a")],"road","lga")
        self.assertEqual(list(packs),["shared-localities"])

    def test_duplicate_pfi_and_unknown_locality_require_review(self):
        rows=[candidate("a",1),candidate("b",1),candidate("c",2,["OTHER"])]
        ledger=[entry("a"),entry("b"),entry("c")]
        packs, exceptions, manifest=stage({"features":rows},ledger,"road","lga")
        self.assertEqual(packs,{})
        self.assertEqual(manifest["excludedFromStaging"],3)
        self.assertEqual(sum(x["reason"]=="shared_source_pfi_requires_review" for x in exceptions),2)

    def test_unaudited_candidate_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"independent audit"):
            stage({"features":[candidate("a",1)]}, [],"road","lga")


if __name__ == "__main__":
    unittest.main()
