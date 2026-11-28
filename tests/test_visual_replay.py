import datetime as dt
import io
import urllib.error
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
        with patch.object(visual_replay.urllib.request, "urlopen", return_value=FakeResponse({"values": self._values(now)})):
            bars = fetch("15min", dt.timedelta(minutes=15), 2, now)
        times = [bar["time"] for bar in bars]
        self.assertIn("2026-11-28 10:15:00", times)
        self.assertNotIn("2026-11-28 10:30:00", times)

    def test_parses_date_only_daily_candle_timestamp(self):
        stamp = visual_replay.parse_utc("2026-11-27")
        self.assertEqual(stamp, dt.datetime(2026, 11, 27, tzinfo=dt.timezone.utc))

    def test_checkpoints_begin_after_all_timeframes_have_20_candles(self):
        histories = {}
        base = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
        for interval, label, delta in visual_replay.TFS:
            count = int(dt.timedelta(days=900) / delta) + 30
            histories[label] = [
                {"time": (base + delta * i).strftime("%Y-%m-%d %H:%M:%S")}
                for i in range(count)
            ]
        checkpoints = visual_replay.build_checkpoints(histories, 3)
        first = checkpoints[0]
        for _, label, _delta in visual_replay.TFS:
            available = [
                bar for bar in histories[label]
                if visual_replay.parse_utc(bar["time"]) <= first
            ]
            self.assertGreaterEqual(len(available), 20)

    def test_checkpoints_fail_when_timeframes_do_not_overlap_after_warmup(self):
        histories = {}
        base = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
        for _interval, label, delta in visual_replay.TFS:
            histories[label] = [
                {"time": (base + delta * i).strftime("%Y-%m-%d %H:%M:%S")}
                for i in range(20)
            ]
        with self.assertRaisesRegex(RuntimeError, "Insufficient overlapping"):
            visual_replay.build_checkpoints(histories, 2)

    def test_rejects_invalid_ohlc_order(self):
        now = dt.datetime(2026, 11, 28, 10, 40, tzinfo=dt.timezone.utc)
        with patch.object(visual_replay.urllib.request, "urlopen", return_value=FakeResponse({"values": self._values(now, invalid=True)})):
            with self.assertRaisesRegex(RuntimeError, "invalid OHLC ordering"):
                fetch("15min", dt.timedelta(minutes=15), 2, now)

    def test_retries_twelve_data_http_429(self):
        now = dt.datetime(2026, 11, 28, 10, 40, tzinfo=dt.timezone.utc)
        limited = urllib.error.HTTPError(
            "https://api.twelvedata.com/time_series", 429, "Too Many Requests",
            {"Retry-After": "0"}, io.BytesIO(b'{"message":"rate limited"}'),
        )
        with patch.object(
            visual_replay.urllib.request, "urlopen",
            side_effect=[limited, FakeResponse({"values": self._values(now)})],
        ) as mocked, patch.object(visual_replay.time, "sleep") as sleeper:
            bars = fetch("15min", dt.timedelta(minutes=15), 2, now)
        self.assertGreaterEqual(len(bars), 20)
        self.assertEqual(mocked.call_count, 2)
        sleeper.assert_called_once_with(5.0)


if __name__ == "__main__":
    unittest.main()
