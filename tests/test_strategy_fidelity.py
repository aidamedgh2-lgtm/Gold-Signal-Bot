import unittest
from strategy_fidelity import (
    approach_points, count_zone_visits, decision_for_score, departure_strength_points,
    duration_points, duration_points_by_timeframe, hierarchical_mtf_points,
    reward_risk_points, score_six_criteria, visit_points,
    matching_lower_timeframes,
)

def bar(low, high):
    return {"low": low, "high": high}

class FidelityTests(unittest.TestCase):
    def test_visual_unknowns_are_not_scored(self):
        self.assertIsNone(departure_strength_points(None))
        self.assertIsNone(departure_strength_points("uncertain"))
        self.assertIsNone(approach_points(None))
        self.assertIsNone(approach_points("uncertain"))
        self.assertEqual(departure_strength_points("sharp"), 2)
        self.assertEqual(departure_strength_points("diagonal"), 1)
        self.assertEqual(approach_points("fast"), 1)

    def test_rr_thresholds(self):
        self.assertEqual(reward_risk_points(10, 9, 13, "DEMAND"), (3.0, 2))
        self.assertEqual(reward_risk_points(10, 9, 12, "DEMAND"), (2.0, 1))
        self.assertEqual(reward_risk_points(10, 9, 11, "DEMAND"), (1.0, 0))

    def test_rr_supply_direction(self):
        self.assertEqual(reward_risk_points(10, 11, 7, "SUPPLY"), (3.0, 2))

    def test_mtf_hierarchy_two_and_three_frames(self):
        self.assertEqual(hierarchical_mtf_points(["MN1", "W1", "D1"]), 2)
        self.assertEqual(hierarchical_mtf_points(["W1", "D1", "H4"]), 2)
        self.assertEqual(hierarchical_mtf_points(["D1", "H4"]), 1)
        self.assertEqual(hierarchical_mtf_points(["MN1", "D1"]), 1)
        self.assertEqual(hierarchical_mtf_points(["H4", "H1"]), 1)
        self.assertEqual(hierarchical_mtf_points(["MN1", "D1", "H1"]), 2)

    def test_lower_timeframe_confirmation_requires_same_direction_and_overlap(self):
        parent = {"direction": "DEMAND", "low": 2300.0, "high": 2310.0}
        candidates = {
            "H1": [
                {"direction": "DEMAND", "low": 2305.0, "high": 2315.0},
            ],
            "M15": [
                {"direction": "DEMAND", "low": 2308.0, "high": 2312.0},
            ],
        }
        result = matching_lower_timeframes("H4", parent, candidates)
        self.assertEqual(result["aligned_timeframes"], ["H4", "H1", "M15"])
        self.assertEqual(result["points"], 2)

    def test_lower_timeframe_direction_or_zone_mismatch_does_not_confirm(self):
        parent = {"direction": "DEMAND", "low": 2300.0, "high": 2310.0}
        candidates = {
            "H1": [{"direction": "SUPPLY", "low": 2305.0, "high": 2308.0}],
            "M15": [{"direction": "DEMAND", "low": 2311.0, "high": 2315.0}],
        }
        result = matching_lower_timeframes("H4", parent, candidates)
        self.assertEqual(result["aligned_timeframes"], ["H4"])
        self.assertEqual(result["points"], 0)

    def test_two_timeframes_get_one_point_three_get_two(self):
        parent = {"direction": "SUPPLY", "low": 2400.0, "high": 2410.0}
        one_match = {"H1": [{"direction": "SUPPLY", "low": 2405.0, "high": 2415.0}]}
        two_matches = {
            **one_match,
            "M15": [{"direction": "SUPPLY", "low": 2402.0, "high": 2408.0}],
        }
        self.assertEqual(matching_lower_timeframes("H4", parent, one_match)["points"], 1)
        self.assertEqual(matching_lower_timeframes("H4", parent, two_matches)["points"], 2)

    def test_contiguous_touches_are_one_visit(self):
        bars = [bar(20, 21), bar(9, 10), bar(9.5, 10.5), bar(20, 21),
                bar(9, 10), bar(20, 21), bar(9, 10)]
        self.assertEqual(count_zone_visits(bars, 9, 10, 0), 3)
        self.assertEqual(visit_points(0), 2)
        self.assertEqual(visit_points(1), 2)
        self.assertEqual(visit_points(2), 1)
        self.assertEqual(visit_points(3), 0)

    def test_duration_counts_touches_not_base_length(self):
        bars = [bar(9, 10), bar(10, 11), bar(20, 21), bar(9.5, 10.5), bar(20, 21)]
        self.assertEqual(duration_points(bars, 9, 10), (1, 3))
        self.assertEqual(duration_points(bars * 2, 9, 10), (0, 6))

    def test_duration_requires_d1_h4_agreement(self):
        result = duration_points_by_timeframe([bar(9, 10)] * 3, [bar(9, 10)] * 5, 9, 10)
        self.assertIsNone(result["score"])
        self.assertEqual(result["d1_count"], 3)
        self.assertEqual(result["h4_count"], 5)

    def test_total_withheld_until_all_criteria_verified(self):
        incomplete = score_six_criteria(
            departure_visual="uncertain", approach_visual=None,
            rr_points=2, mtf_points=2, visits=0, duration_points_value=1)
        self.assertFalse(incomplete["complete"])
        self.assertIsNone(incomplete["total"])
        complete = score_six_criteria(
            departure_visual="sharp", approach_visual="fast",
            rr_points=2, mtf_points=2, visits=0, duration_points_value=1)
        self.assertTrue(complete["complete"])
        self.assertEqual(complete["total"], 10)

    def test_pdf_decision_thresholds(self):
        self.assertEqual(decision_for_score(10), "pending_candidate")
        self.assertEqual(decision_for_score(9), "pending_candidate")
        self.assertEqual(decision_for_score(8), "monitor")
        self.assertEqual(decision_for_score(7), "monitor")
        self.assertEqual(decision_for_score(6), "reject")
        self.assertEqual(decision_for_score(None), "incomplete")

if __name__ == "__main__":
    unittest.main()
