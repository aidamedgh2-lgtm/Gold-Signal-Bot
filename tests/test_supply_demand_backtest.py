import unittest

import supply_demand_backtest as bt


class SupplyDemandBacktestTests(unittest.TestCase):
    def test_month_end_is_next_month_start(self):
        start = bt.parse_time("2026-01-01 00:00:00")
        self.assertEqual(bt.candle_end(start, "month").isoformat(),
                         "2026-02-01T00:00:00+00:00")

    def test_only_closed_candles_are_selected_at_decision_time(self):
        end_times = [
            bt.parse_time("2026-11-27 10:15:00"),
            bt.parse_time("2026-11-27 10:30:00"),
            bt.parse_time("2026-11-27 10:45:00"),
        ]
        decision = bt.parse_time("2026-11-27 10:30:00")
        import bisect
        self.assertEqual(bisect.bisect_right(end_times, decision), 2)

    def test_buy_stop_first_when_both_levels_touch(self):
        bars = [
            {"time": "a", "open": 100, "high": 101, "low": 99.5, "close": 100},
            {"time": "b", "open": 100, "high": 103, "low": 98, "close": 101},
        ]
        result = bt.simulate_trade(bars, 0, "BUY", 100, 99, cost_r=0)
        self.assertEqual(result["exit_reason"], "stop_and_tp_same_bar_stop_first")
        self.assertEqual(result["net_r"], -1)

    def test_sell_stop_first_when_both_levels_touch(self):
        bars = [
            {"time": "a", "open": 100, "high": 100.5, "low": 99, "close": 100},
            {"time": "b", "open": 100, "high": 102, "low": 97, "close": 99},
        ]
        result = bt.simulate_trade(bars, 0, "SELL", 100, 101, cost_r=0)
        self.assertEqual(result["exit_reason"], "stop_and_tp_same_bar_stop_first")
        self.assertEqual(result["net_r"], -1)

    def test_profit_factor_undefined_without_losses(self):
        summary = bt.summarize([{"net_r": 1.5}])
        self.assertIsNone(summary["profit_factor"])
        self.assertEqual(summary["win_rate_pct"], 100)


if __name__ == "__main__":
    unittest.main()
