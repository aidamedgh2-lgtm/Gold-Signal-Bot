import os
import unittest
from unittest.mock import patch

os.environ.setdefault("TWELVEDATA_API_KEY", "offline-test-key")

import backtest
import forward_test
import supply_demand_live


def candle(stamp, open_, high, low, close):
    return {
        "time": stamp,
        "open": float(open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
    }


class HistoricalBacktestExecutionTests(unittest.TestCase):
    def setUp(self):
        self.signal = {
            0: {"direction": "BUY", "stop": 99.0, "risk": 1.0}
        }

    def test_entry_candle_stop_is_counted(self):
        bars = [
            candle("2026-11-27 12:00:00", 100, 101, 99.5, 100),
            candle("2026-11-27 12:15:00", 100, 101, 98, 99),
            candle("2026-11-27 12:30:00", 99, 100, 98.5, 99),
        ]
        trades = backtest.simulate(bars, self.signal, "test")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["r_multiple"], -1.0)
        self.assertEqual(trades[0]["exit_reason"], "stop")
        self.assertEqual(trades[0]["exit_time"], bars[1]["time"])

    def test_stop_wins_when_stop_and_target_touch_same_entry_candle(self):
        bars = [
            candle("2026-11-27 12:00:00", 100, 101, 99.5, 100),
            candle("2026-11-27 12:15:00", 100, 102.5, 98, 100),
        ]
        trades = backtest.simulate(bars, self.signal, "test")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["r_multiple"], -1.0)
        self.assertEqual(trades[0]["exit_reason"], "stop")


    def test_entry_candle_target_is_counted(self):
        bars = [
            candle("2026-11-27 12:00:00", 100, 101, 99.5, 100),
            candle("2026-11-27 12:15:00", 100, 102.5, 99.5, 102),
        ]
        trades = backtest.simulate(bars, self.signal, "test")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["r_multiple"], 2.0)
        self.assertEqual(trades[0]["exit_reason"], "target")

    def test_gap_through_sell_stop_rejects_entry(self):
        bars = [
            candle("2026-11-27 12:00:00", 100, 100.5, 99.5, 100),
            candle("2026-11-27 12:15:00", 102, 102.5, 101.5, 102),
        ]
        signal = {0: {"direction": "SELL", "stop": 101.0, "risk": 1.0}}
        self.assertEqual(backtest.simulate(bars, signal, "test"), [])

    def test_higher_timeframe_aggregation_requires_complete_bucket(self):
        complete = [
            candle("2026-11-27 12:00:00", 100, 101, 99, 100),
            candle("2026-11-27 12:15:00", 100, 102, 99, 101),
            candle("2026-11-27 12:30:00", 101, 103, 100, 102),
            candle("2026-11-27 12:45:00", 102, 104, 101, 103),
        ]
        self.assertEqual(len(backtest.aggregate(complete, 1)), 1)
        incomplete = complete[:2] + complete[3:]
        self.assertEqual(backtest.aggregate(incomplete, 1), [])

    def test_gap_through_buy_stop_rejects_entry(self):
        bars = [
            candle("2026-11-27 12:00:00", 100, 101, 99.5, 100),
            candle("2026-11-27 12:15:00", 98.5, 99, 98, 98.7),
        ]
        self.assertEqual(backtest.simulate(bars, self.signal, "test"), [])


class ForwardPaperExecutionTests(unittest.TestCase):
    def _state(self):
        return {
            "test_start_utc": "2026-11-26T00:00:00+00:00",
            "books": {
                "ICT": {"active": None, "trades": []},
                "ICT + Fibonacci Classic": {"active": None, "trades": []},
            },
        }

    def test_entry_candle_stop_is_counted_for_both_books(self):
        bars = [
            candle("2026-11-27 12:00:00", 100, 101, 99.5, 100),
            candle("2026-11-27 12:15:00", 100, 101, 98, 99),
        ]
        signal = {"direction": "BUY", "stop": 99.0, "risk": 1.0}
        with patch.object(forward_test, "atr", return_value=1.0), \
             patch.object(forward_test, "live_ict_candidate", return_value=signal), \
             patch.object(forward_test, "fibonacci_classic_near", return_value=True):
            state = self._state()
            forward_test.process_bar(state, bars, 1)
        for book in state["books"].values():
            self.assertEqual(len(book["trades"]), 1)
            self.assertEqual(book["trades"][0]["r"], -1.0)
            self.assertEqual(book["trades"][0]["exit_reason"], "stop")
            self.assertIsNone(book["active"])

    def test_gap_through_buy_stop_rejects_forward_entry(self):
        bars = [
            candle("2026-11-27 12:00:00", 100, 101, 99.5, 100),
            candle("2026-11-27 12:15:00", 98.5, 99, 98, 98.7),
        ]
        signal = {"direction": "BUY", "stop": 99.0, "risk": 1.0}
        with patch.object(forward_test, "atr", return_value=1.0), \
             patch.object(forward_test, "live_ict_candidate", return_value=signal), \
             patch.object(forward_test, "fibonacci_classic_near", return_value=True):
            state = self._state()
            forward_test.process_bar(state, bars, 1)
        for book in state["books"].values():
            self.assertEqual(book["trades"], [])
            self.assertIsNone(book["active"])


class LiveConfirmationTests(unittest.TestCase):
    def test_demand_bullish_engulfing_confirms(self):
        bars = [
            candle("2026-11-27 11:45:00", 100, 101, 99, 100),
            candle("2026-11-27 12:00:00", 100.5, 100.8, 99.2, 99.5),
            candle("2026-11-27 12:15:00", 99.4, 100.8, 99.3, 100.6),
        ]
        zone = {"direction": "DEMAND", "low": 99.0, "high": 100.0}
        self.assertEqual(supply_demand_live.confirmation(bars, zone), "Engulfing")

    def test_supply_bearish_engulfing_confirms(self):
        bars = [
            candle("2026-11-27 11:45:00", 100, 101, 99, 100),
            candle("2026-11-27 12:00:00", 99.5, 100.8, 99.2, 100.5),
            candle("2026-11-27 12:15:00", 100.6, 100.7, 99.2, 99.4),
        ]
        zone = {"direction": "SUPPLY", "low": 100.0, "high": 101.0}
        self.assertEqual(supply_demand_live.confirmation(bars, zone), "Engulfing")

    def test_confirmation_rejected_when_neither_candle_touches_zone(self):
        bars = [
            candle("2026-11-27 11:45:00", 100, 101, 99.5, 100),
            candle("2026-11-27 12:00:00", 100, 101, 99.5, 100.5),
            candle("2026-11-27 12:15:00", 100.5, 101.5, 100, 101),
        ]
        zone = {"direction": "DEMAND", "low": 95.0, "high": 96.0}
        self.assertIsNone(supply_demand_live.confirmation(bars, zone))


if __name__ == "__main__":
    unittest.main()
