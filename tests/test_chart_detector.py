import unittest
import io
from PIL import Image

from services.chart_detector import (
    map_normalized_bbox_to_market, validate_zone_result, render_market_chart,
)


BARS = [
    {"time": f"2026-01-{i:02d} 00:00:00", "open": 60+i, "high": 65+i,
     "low": 55+i, "close": 62+i}
    for i in range(1, 25)
]
CAL = {
    "image_width": 1000, "image_height": 1000,
    "axes_left": 100, "axes_right": 900,
    "axes_bottom": 100, "axes_top": 900,
    "xlim": [-1, 24], "ylim": [0, 100],
}


class ChartDetectorTests(unittest.TestCase):
    def test_rendered_image_is_cropped_to_plot_and_calibration_matches(self):
        image_bytes, calibration = render_market_chart(BARS, "H1")
        with Image.open(io.BytesIO(image_bytes)) as image:
            self.assertEqual(image.size, (
                calibration["image_width"], calibration["image_height"]
            ))
        self.assertEqual(calibration["axes_left"], 0.0)
        self.assertEqual(calibration["axes_bottom"], 0.0)
        self.assertEqual(calibration["axes_right"], calibration["image_width"])
        self.assertEqual(calibration["axes_top"], calibration["image_height"])
        self.assertGreater(calibration["image_width"], 0)
        self.assertGreater(calibration["image_height"], 0)

    def test_pixel_bbox_maps_to_calibrated_prices_and_times(self):
        mapped = map_normalized_bbox_to_market([0.2, 0.3, 0.4, 0.4], CAL, BARS)
        self.assertAlmostEqual(mapped["high"], 75.0)
        self.assertAlmostEqual(mapped["low"], 62.5)
        self.assertEqual(mapped["origin_start"], BARS[2]["time"])
        self.assertEqual(mapped["origin_end"], BARS[8]["time"])

    def test_zone_uses_exact_last_pre_impulse_candle_wick_range(self):
        result = validate_zone_result({"zones": [{
            "direction": "DEMAND", "origin_candle_index": 7,
            "departure": "sharp", "confidence": 0.88,
            "evidence": "Final candle before a visually sharp upward impulse"
        }]}, BARS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["direction"], "DEMAND")
        self.assertEqual(result[0]["origin_candle_index"], 7)
        self.assertEqual(result[0]["low"], BARS[7]["low"])
        self.assertEqual(result[0]["high"], BARS[7]["high"])
        self.assertEqual(result[0]["origin_start"], BARS[7]["time"])
        self.assertEqual(result[0]["origin_end"], BARS[7]["time"])
        self.assertEqual(result[0]["boundary_method"],
                         "origin_candle_full_wick_low_high")

    def test_diagonal_is_retained_for_lower_timeframe_confirmation(self):
        result = validate_zone_result({"zones": [{
            "direction": "DEMAND", "origin_candle_index": 7,
            "departure": "diagonal", "confidence": 0.99,
            "evidence": "Strong directional but slanted departure"
        }]}, BARS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["departure"], "diagonal")

    def test_sideways_and_uncertain_departures_are_rejected_immediately(self):
        for departure in ("sideways", "uncertain"):
            with self.subTest(departure=departure):
                result = validate_zone_result({"zones": [{
                    "direction": "DEMAND", "origin_candle_index": 7,
                    "departure": departure, "confidence": 0.99,
                    "evidence": "Not a directional impulse"
                }]}, BARS)
                self.assertEqual(result, [])

    def test_invalid_origin_index_is_rejected(self):
        for index in (-1, len(BARS), True, 2.5):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    validate_zone_result({"zones": [{
                        "direction": "SUPPLY", "origin_candle_index": index,
                        "departure": "sharp", "confidence": 0.9,
                        "evidence": "Visible impulse"
                    }]}, BARS)

    def test_zone_outside_plot_axes_is_rejected(self):
        with self.assertRaises(ValueError):
            map_normalized_bbox_to_market([0.01, 0.3, 0.4, 0.4], CAL, BARS)

    def test_malformed_or_unordered_bbox_is_rejected(self):
        with self.assertRaises(ValueError):
            map_normalized_bbox_to_market([0.4, 0.3, 0.2, 0.4], CAL, BARS)

    def test_unknown_departure_is_not_scored(self):
        result = validate_zone_result({"zones": [{
            "direction": "SUPPLY", "origin_candle_index": 5,
            "departure": "uncertain",
            "confidence": 0.9, "evidence": "Cannot classify"
        }]}, BARS)
        self.assertEqual(result, [])

    def test_invalid_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_zone_result({"unexpected": []}, BARS, CAL)


if __name__ == "__main__":
    unittest.main()
