"""Phase 4 non-field readiness: fail-closed invariants. No physical GPS or DB writes."""
import copy
import json
import unittest
from pathlib import Path
from scripts.check_phase4_nonfield_gate import ROOT, REQUIRED_CHECKS, audit


class NonFieldGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((ROOT / "docs/phase4-nonfield-readiness.json").read_text())

    def test_current_ten_offline_packages_and_inventory_integrity(self):
        errors, blockers = audit()
        self.assertEqual(errors, [], errors)
        self.assertTrue(blockers, "no physical field authorisation until pre-field completion")

    def test_full_nonfield_checklist_is_explicitly_recorded(self):
        self.assertEqual(set(self.record["checks"]), REQUIRED_CHECKS)
        self.assertEqual(self.record["fieldTesting"]["authorised"], False)
        self.assertTrue(all(self.record["restrictions"].values()))

    def test_no_approval_merely_by_marking_ci_checks_green(self):
        false_approval = copy.deepcopy(self.record)
        for item in false_approval["checks"].values():
            item["status"] = "verified"
            item["evidence"] = "synthetic:test"
        false_approval["fieldTesting"] = {
            "authorised": True, "authorisationEvidence": "synthetic:test"
        }
        errors, blockers = audit(readiness=false_approval)
        self.assertTrue(blockers, "remaining unresolved source candidates must block")
        self.assertIn("field testing marked authorised while non-field checks remain open", errors)

    def test_missing_verified_evidence_is_a_hard_error(self):
        corrupted = copy.deepcopy(self.record)
        corrupted["checks"]["all_source_feature_dispositions"]["status"] = "verified"
        errors, _ = audit(readiness=corrupted)
        self.assertIn("missing evidence for verified criterion all_source_feature_dispositions", errors)

    def test_inventories_cannot_be_silently_rounded_or_promoted(self):
        corrupted = copy.deepcopy(self.record)
        corrupted["inventory"]["blocks"]["requiring_evidence"] = 0
        errors, _ = audit(readiness=corrupted)
        self.assertIn("candidate block dispositions do not reconcile", errors)


    def test_class0_verified_unsupported_cases_have_explicit_pfi_evidence(self):
        source = json.loads((ROOT / "docs/phase4-verified-unsupported-class0-freeways-20261015.json").read_text(encoding="utf-8"))
        entries = source["records"]
        self.assertEqual(len(entries), 8)
        self.assertEqual(len({row["candidateId"] for row in entries}), 8)
        self.assertEqual(self.record["inventory"]["blocks"]["unsupported_for_vehicular_lookup"], 23 + len(entries))
        self.assertEqual(self.record["inventory"]["blocks"]["requiring_evidence"], 226 - 23 - len(entries))
        self.assertEqual({row["disposition"] for row in entries}, {"VERIFIED_UNSUPPORTED"})
        self.assertEqual({row["physicalVerificationStatus"] for row in entries}, {"NOT_PERFORMED"})
        self.assertTrue(all(row["publicationEligible"] is False for row in entries))
        for row in entries:
            n = len(row["sourcePFIs"])
            self.assertGreater(n, 0)
            self.assertEqual(len(row["networkUFIEndpoints"]), n)
            self.assertEqual(row["classCodes"], [0] * n)
            self.assertEqual(row["vehicularAccessCodes"], ["1"] * n)
            self.assertEqual(row["roadStatusCodes"], ["O"] * n)
            self.assertTrue("WEST GATE" in row["street"])


if __name__ == "__main__":
    unittest.main()
