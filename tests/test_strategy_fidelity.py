import unittest

from strategy_fidelity import (
    approach_points, count_zone_visits, departure_strength_points,
    duration_points, hierarchical_mtf_points, reward_risk_points,
    score_six_criteria, visit_points,
)


def bar(low, high):
    return {"low": low, "high": high}


class FidelityTests(unittest.TestCase):
    def test_visual_inputs_are_not_guessed(self):
        self.assertIsNone(departure_strength_points(None))
        self.assertIsNone(approach_points(None))
        self.assertEqual(departure_strength_points("sharp"), 2)
        self.assertEqual(departure_strength_points("diagonal"), 1)
        self.assertEqual(approach_points("fast"), 1)

    def test_rr_thresholds(self):
        self.assertEqual(reward_risk_points(10, 9, 13, "DEMAND"), (3.0, 2))
        self.assertEqual(reward_risk_points(10, 9, 12, "DEMAND"), (2.0, 1))
        self.assertEqual(reward_risk_points(10, 9, 11, "DEMAND"), (1.0, 0))

    def test_rr_supply_direction(self):
        ratio, points = reward_risk_points(10, 11, 7, "SUPPLY")
        self.assertEqual((ratio, points), (3.0, 2))

    def test_only_hierarchical_triplets_score(self):
        self.assertEqual(hierarchical_mtf_points(["MN1", "W1", "D1"]), 2)
        self.assertEqual(hierarchical_mtf_points(["W1", "D1", "H4"]), 2)
        self.assertEqual(hierarchical_mtf_points(["MN1", "D1", "H1"]), 0)
        self.assertEqual(hierarchical_mtf_points(["D1", "H4"]), 0)

    def test_contiguous_touches_are_one_visit(self):
        bars = [bar(20, 21), bar(9, 10), bar(9.5, 10.5), bar(20, 21),
                bar(9, 10), bar(20, 21), bar(9, 10)]
        self.assertEqual(count_zone_visits(bars, 9, 10, 0), 3)
        self.assertEqual(visit_points(1), 2)
        self.assertEqual(visit_points(2), 1)
        self.assertEqual(visit_points(3), 0)

    def test_duration_counts_zone_touching_bars_not_base_length(self):
        bars = [bar(9, 10), bar(10, 11), bar(20, 21), bar(9.5, 10.5), bar(20, 21)]
        self.assertEqual(duration_points(bars, 9, 10), (1, 3))
        self.assertEqual(duration_points(bars * 2, 9, 10), (0, 6))

    def test_total_is_withheld_until_visual_review_complete(self):
        result = score_six_criteria(
            departure_visual=None, approach_visual=None, rr_points=2,
            mtf_points=2, visits=1, duration_points_value=1)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["total"])
        complete = score_six_criteria(
            departure_visual="sharp", approach_visual="fast", rr_points=2,
            mtf_points=2, visits=1, duration_points_value=1)
        self.assertTrue(complete["complete"])
        self.assertEqual(complete["total"], 10)


if __name__ == "__main__":
    unittest.main()
