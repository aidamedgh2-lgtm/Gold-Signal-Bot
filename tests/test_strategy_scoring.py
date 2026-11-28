import unittest

import supply_demand_live as live


class OpposingZoneRiskRewardTests(unittest.TestCase):
    def test_demand_uses_nearest_supply_zone_lower_boundary(self):
        demand = {"direction": "DEMAND", "low": 100.0, "high": 102.0, "stop": 99.0}
        near_supply = {"direction": "SUPPLY", "low": 106.0, "high": 108.0}
        far_supply = {"direction": "SUPPLY", "low": 112.0, "high": 114.0}
        live.apply_opposing_zone_rr(demand, [demand, far_supply, near_supply])
        self.assertEqual(demand["target"], 106.0)
        self.assertAlmostEqual(demand["rr"], 2.5)
        self.assertEqual(demand["rr_points"], 1)

    def test_supply_uses_nearest_demand_zone_upper_boundary(self):
        supply = {"direction": "SUPPLY", "low": 108.0, "high": 110.0, "stop": 111.0}
        near_demand = {"direction": "DEMAND", "low": 102.0, "high": 104.0}
        far_demand = {"direction": "DEMAND", "low": 96.0, "high": 98.0}
        live.apply_opposing_zone_rr(supply, [supply, far_demand, near_demand])
        self.assertEqual(supply["target"], 104.0)
        self.assertAlmostEqual(supply["rr"], 2.5)
        self.assertEqual(supply["rr_points"], 1)

    def test_missing_opposing_zone_is_not_replaced_by_historical_extreme(self):
        demand = {"direction": "DEMAND", "low": 100.0, "high": 102.0, "stop": 99.0}
        live.apply_opposing_zone_rr(demand, [demand])
        self.assertIsNone(demand["target"])
        self.assertEqual(demand["rr"], 0.0)
        self.assertEqual(demand["rr_points"], 0)

    def test_invalid_risk_receives_zero_points(self):
        demand = {"direction": "DEMAND", "low": 100.0, "high": 102.0, "stop": 101.0}
        supply = {"direction": "SUPPLY", "low": 106.0, "high": 108.0}
        live.apply_opposing_zone_rr(demand, [demand, supply])
        self.assertEqual(demand["rr_points"], 0)


if __name__ == "__main__":
    unittest.main()
