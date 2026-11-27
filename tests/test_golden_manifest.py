import json
import unittest
from pathlib import Path


class GoldenCaseManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "golden_cases" / "manifest.json"
        cls.manifest = json.loads(path.read_text(encoding="utf-8"))

    def test_manifest_has_unique_source_cases(self):
        cases = self.manifest["cases"]
        ids = [case["case_id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(cases), 6)
        for case in cases:
            self.assertTrue(case["source_pages"])
            self.assertIn("label_status", case)

    def test_six_pdf_weights_sum_to_ten(self):
        weights = self.manifest["cases"]
        score_case = next(case for case in weights if case["case_id"] == "PDF-SCORE-01")
        self.assertEqual(sum(score_case["expected_weights"].values()), 10)
        self.assertEqual(score_case["expected_total"], 10)

    def test_ambiguous_zone_boundaries_remain_unlabelled(self):
        case = next(case for case in self.manifest["cases"]
                    if case["case_id"] == "PDF-ZONE-BOUNDARY-01")
        self.assertEqual(case["label_status"], "incomplete")
        self.assertIsNone(case["machine_coordinates"])

    def test_visual_criteria_are_not_replaced_with_numeric_proxies(self):
        policy = self.manifest["acceptance_policy"]
        self.assertTrue(policy["no_atr_or_fixed_numeric_proxy_for_visual_criteria"])
        self.assertTrue(policy["unknown_is_valid"])
        self.assertTrue(policy["do_not_enable_live_signals_until_zone_boundaries_and_all_six_criteria_pass_review"])


if __name__ == "__main__":
    unittest.main()
