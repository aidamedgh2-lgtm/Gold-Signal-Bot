import unittest

import supply_demand_backtest as bt


class SupplyDemandBacktestTests(unittest.TestCase):
    def test_valid_ohlc_accepts_consistent_positive_candle(self):
        self.assertTrue(bt.valid_ohlc({
            "open": 2000.0, "high": 2010.0, "low": 1990.0, "close": 2005.0
        }))

    def test_valid_ohlc_rejects_inconsistent_candle(self):
        self.assertFalse(bt.valid_ohlc({
            "open": 2000.0, "high": 1990.0, "low": 1980.0, "close": 2005.0
        }))

    def test_valid_ohlc_rejects_non_positive_price(self):
        self.assertFalse(bt.valid_ohlc({
            "open": 0.0, "high": 2010.0, "low": 1990.0, "close": 2005.0
        }))

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

    def test_identical_duplicate_timestamp_is_deduplicated(self):
        start = bt.parse_time("2026-01-01 00:00:00")
        row = {"time": "2026-01-01", "open": 1.0, "high": 2.0,
               "low": 0.5, "close": 1.5, "_start": start, "_end": start}
        bars, count = bt.deduplicate_bars([row, dict(row)], "MN1")
        self.assertEqual(len(bars), 1)
        self.assertEqual(count, 1)

    def test_conflicting_duplicate_timestamp_is_rejected(self):
        start = bt.parse_time("2026-01-01 00:00:00")
        first = {"time": "2026-01-01", "open": 1.0, "high": 2.0,
                 "low": 0.5, "close": 1.5, "_start": start, "_end": start}
        second = dict(first, close=1.6)
        with self.assertRaisesRegex(RuntimeError, "conflicting duplicate timestamp"):
            bt.deduplicate_bars([first, second], "MN1")

    def test_mtf_match_uses_other_zone_atr_for_distance_filter(self):
        candidate = {
            "low": 100.0, "high": 101.0, "atr": 10.0,
            "direction": "DEMAND", "tf": "H4",
            "move_points": 1, "rr_points": 1, "visit_points": 1,
            "duration_points": 1, "arrival_points": 0, "move_atr": 1.5,
        }
        nearby_other = {
            "low": 101.5, "high": 102.5, "atr": 0.1,
            "direction": "DEMAND", "tf": "H1",
            "move_points": 1, "rr_points": 1, "visit_points": 1,
            "duration_points": 1, "arrival_points": 0, "move_atr": 1.5,
        }
        candidates = bt.score_candidates([candidate, nearby_other], price=100.0)
        h4_candidate = next(item for item in candidates if item["tf"] == "H4")
        self.assertEqual(h4_candidate["matches"], [])

    def test_profit_factor_undefined_without_losses(self):
        summary = bt.summarize([{"net_r": 1.5}])
        self.assertIsNone(summary["profit_factor"])
        self.assertEqual(summary["win_rate_pct"], 100)

    def test_intraday_pagination_cursor_moves_before_oldest_candle(self):
        import datetime as dt
        oldest = dt.datetime(2026, 11, 27, 10, 0, tzinfo=dt.timezone.utc)
        cursor = bt.page_cursor_before(oldest)
        self.assertEqual(cursor, oldest - dt.timedelta(seconds=1))
        self.assertLess(cursor, oldest)

    def test_intraday_history_window_rejects_invalid_days(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"SD_INTRADAY_HISTORY_DAYS": "0"}):
            with self.assertRaisesRegex(RuntimeError, "between 1 and 365"):
                bt.fetch_history("1min", "M1", "1min")

if __name__ == "__main__":
    unittest.main()
