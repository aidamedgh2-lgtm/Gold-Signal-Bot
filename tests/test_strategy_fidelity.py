import unittest

from strategy_fidelity import (
    zone_duration_points, count_zone_visits, visit_points,
    hierarchical_mtf_matches, mtf_points, opposing_zone_target, rr_from_zone,
    approach_shape_proxy,
)


class StrategyFidelityTests(unittest.TestCase):
    def setUp(self):
        self.zone = {"low": 100.0, "high": 102.0, "tf": "H4", "direction": "DEMAND"}

    def bar(self, low, high, close=None):
        return {"low": low, "high": high, "close": close if close is not None else (low + high) / 2}

    def test_duration_counts_touching_candles_not_base_candles(self):
        bars = [self.bar(95, 98)] + [self.bar(101, 103)] * 4
        self.assertEqual(zone_duration_points(bars, self.zone, 0), (1, 4))
        bars.append(self.bar(100, 101))
        self.assertEqual(zone_duration_points(bars, self.zone, 0), (0, 5))

    def test_consecutive_touches_are_one_visit(self):
        bars = [self.bar(95, 98), self.bar(101, 103), self.bar(100, 101),
                self.bar(95, 99), self.bar(101, 103)]
        self.assertEqual(count_zone_visits(bars, self.zone, 0), 2)
        self.assertEqual(visit_points(2), 0)

    def test_mtf_counts_distinct_overlapping_higher_and_lower_frames(self):
        zones = [
            self.zone,
            {"low": 100.5, "high": 103, "tf": "D1", "direction": "DEMAND"},
            {"low": 99.5, "high": 102.5, "tf": "H1", "direction": "DEMAND"},
        ]
        matches = hierarchical_mtf_matches(self.zone, zones)
        self.assertEqual(matches, ["D1", "H1"])
        self.assertEqual(mtf_points(matches), 2)

    def test_target_is_nearest_opposing_zone_not_rolling_extreme(self):
        zones = [self.zone,
                 {"low": 106, "high": 108, "tf": "H1", "direction": "SUPPLY"},
                 {"low": 110, "high": 112, "tf": "D1", "direction": "SUPPLY"}]
        self.assertEqual(opposing_zone_target(self.zone, zones), 106)

    def test_rr_requires_a_real_opposing_zone(self):
        rr, points = rr_from_zone(self.zone, None, 99)
        self.assertEqual((rr, points), (0.0, 0))
        rr, points = rr_from_zone(self.zone, 106, 99)
        self.assertAlmostEqual(rr, 2.0)
        self.assertEqual(points, 1)

    def test_approach_proxy_distinguishes_clean_directional_approach(self):
        bars = [self.bar(110, 111, 110), self.bar(108, 109, 108),
                self.bar(106, 107, 106), self.bar(104, 105, 104),
                self.bar(102, 103, 102), self.bar(101, 102, 101)]
        self.assertTrue(approach_shape_proxy(bars, self.zone))


if __name__ == "__main__":
    unittest.main()
