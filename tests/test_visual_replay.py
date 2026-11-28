import datetime as dt
import json
import unittest
from unittest.mock import patch

from backtest.visual_replay import fetch


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.payload


class VisualReplayFetchTests(unittest.TestCase):
    def test_keeps_latest_closed_candle_without_double_dropping(self):
        now = dt.datetime(2026, 11, 28, 10, 40, tzinfo=dt.timezone.utc)
        values = [
            {"datetime": "2026-11-28 10:30:00", "open": "10", "high": "12", "low": "9", "close": "11"},
            {"datetime": "2026-11-28 10:15:00", "open": "10", "high": "12", "low": "9", "close": "11"},
            {"datetime": "2026-11-28 10:00:00", "open": "10", "high": "12", "low": "9", "close": "11"},
        ]
        values += [
            {"datetime": f"2026-11-27 {hour:02d}:00:00", "open": "10", "high": "12", "low": "9", "close": "11"}
            for hour in range(20)
        ]
        with patch("backtest.visual_replay.urllib.request.urlopen", return_value=FakeResponse({"values": values})):
            bars = fetch("15min", "M15", 1, now)
        times = [bar["time"] for bar in bars]
        self.assertIn("2026-11-28 10:15:00", times)
        self.assertNotIn("2026-11-28 10:30:00", times)

    def test_rejects_invalid_ohlc_order(self):
        now = dt.datetime(2026, 11, 28, 10, 40, tzinfo=dt.timezone.utc)
        values = [
            {"datetime": f"2026-11-27 {hour:02d}:00:00", "open": "10", "high": "8", "low": "9", "close": "11"}
            for hour in range(20)
        ]
        with patch("backtest.visual_replay.urllib.request.urlopen", return_value=FakeResponse({"values": values})):
            with self.assertRaisesRegex(RuntimeError, "invalid OHLC ordering"):
                fetch("15min", "M15", 1, now)


if __name__ == "__main__":
    unittest.main()
