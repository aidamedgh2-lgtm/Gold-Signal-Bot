import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

_path = Path(__file__).resolve().parents[1] / "backtest" / "visual_replay.py"
_spec = importlib.util.spec_from_file_location("visual_replay_under_test", _path)
visual_replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(visual_replay)
fetch = visual_replay.fetch


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.payload


class VisualReplayFetchTests(unittest.TestCase):
    def _values(self, now, invalid=False):
        delta = dt.timedelta(minutes=15)
        first = now - dt.timedelta(days=2) + delta
        values = []
        for i in range(20):
            stamp = first + i * delta
            values.append({"datetime": stamp.strftime("%Y-%m-%d %H:%M:%S"),
                "open": "10", "high": "8" if invalid else "12",
                "low": "9", "close": "11"})
        values.extend([
            {"datetime": "2026-11-28 10:30:00", "open": "10", "high": "12", "low": "9", "close": "11"},
            {"datetime": "2026-11-28 10:15:00", "open": "10", "high": "12", "low": "9", "close": "11"},
            {"datetime": "2026-11-28 10:00:00", "open": "10", "high": "12", "low": "9", "close": "11"},
        ])
        return values

    def test_keeps_latest_closed_candle_without_double_dropping(self):
        now = dt.datetime(2026, 11, 28, 10, 40, tzinfo=dt.timezone.utc)
        with patch("visual_replay_under_test.urllib.request.urlopen", return_value=FakeResponse({"values": self._values(now)})):
            bars = fetch("15min", "M15", 2, now)
        times = [bar["time"] for bar in bars]
        self.assertIn("2026-11-28 10:15:00", times)
        self.assertNotIn("2026-11-28 10:30:00", times)

    def test_rejects_invalid_ohlc_order(self):
        now = dt.datetime(2026, 11, 28, 10, 40, tzinfo=dt.timezone.utc)
        with patch("visual_replay_under_test.urllib.request.urlopen", return_value=FakeResponse({"values": self._values(now, invalid=True)})):
            with self.assertRaisesRegex(RuntimeError, "invalid OHLC ordering"):
                fetch("15min", "M15", 2, now)


if __name__ == "__main__":
    unittest.main()
