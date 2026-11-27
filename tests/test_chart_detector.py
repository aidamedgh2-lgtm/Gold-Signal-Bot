import unittest

from services.chart_detector import validate_zone_result


BARS = [
    {"time": f"2026-01-{i:02d} 00:00:00", "open": 100+i, "high": 102+i,
     "low": 99+i, "close": 101+i}
    for i in range(1, 25)
]


class ChartDetectorTests(unittest.TestCase):
    def test_clear_zone_with_real_timestamps_is_accepted(self):
        result = validate_zone_result({"zones": [{
            "direction": "DEMAND", "low": 105.0, "high": 108.0,
            "origin_start": BARS[4]["time"], "origin_end": BARS[6]["time"],
            "departure": "sharp", "boundary_status": "clear",
            "confidence": 0.88, "evidence": "Visible base and sharp departure"
        }]}, BARS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["direction"], "DEMAND")

    def test_unclear_zone_is_rejected_not_guessed(self):
        result = validate_zone_result({"zones": [{
            "direction": "DEMAND", "low": 105.0, "high": 108.0,
            "origin_start": BARS[4]["time"], "origin_end": BARS[6]["time"],
            "departure": "sharp", "boundary_status": "unclear",
            "confidence": 0.99, "evidence": "Ambiguous edges"
        }]}, BARS)
        self.assertEqual(result, [])

    def test_out_of_range_price_is_rejected(self):
        result = validate_zone_result({"zones": [{
            "direction": "SUPPLY", "low": 1.0, "high": 108.0,
            "origin_start": BARS[4]["time"], "origin_end": BARS[6]["time"],
            "departure": "diagonal", "boundary_status": "clear",
            "confidence": 0.9, "evidence": "Visual evidence"
        }]}, BARS)
        self.assertEqual(result, [])

    def test_unknown_departure_is_not_scored(self):
        result = validate_zone_result({"zones": [{
            "direction": "SUPPLY", "low": 110.0, "high": 113.0,
            "origin_start": BARS[4]["time"], "origin_end": BARS[6]["time"],
            "departure": "uncertain", "boundary_status": "clear",
            "confidence": 0.9, "evidence": "Cannot classify"
        }]}, BARS)
        self.assertEqual(result, [])

    def test_invalid_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_zone_result({"unexpected": []}, BARS)


if __name__ == "__main__":
    unittest.main()
