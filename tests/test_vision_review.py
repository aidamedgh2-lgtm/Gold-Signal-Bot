import unittest
from unittest.mock import patch

from services.vision_review import validate_visual_result, load_strategy_reference, review_chart_with_vision


class VisionReviewTests(unittest.TestCase):
    def test_valid_result(self):
        result = validate_visual_result({
            "departure": "sharp", "approach": "fast",
            "zone_readability": "clear", "confidence": 0.91,
            "evidence": "Steep departure and impulsive return.",
            "unknown_reason": "",
        })
        self.assertEqual(result["departure"], "sharp")
        self.assertEqual(result["zone_readability"], "clear")

    def test_uncertain_visuals_are_preserved(self):
        result = validate_visual_result({
            "departure": "uncertain", "approach": "uncertain",
            "zone_readability": "unclear", "confidence": 0.2,
            "evidence": "Not enough context.",
            "unknown_reason": "The chart crop omits the full return.",
        })
        self.assertEqual(result["departure"], "uncertain")
        self.assertEqual(result["zone_readability"], "unclear")

    def test_invalid_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_visual_result({
                "departure": "buy", "approach": "fast",
                "zone_readability": "clear", "confidence": 0.9,
                "evidence": "x", "unknown_reason": "",
            })

    def test_invalid_confidence_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_visual_result({
                "departure": "sharp", "approach": "fast",
                "zone_readability": "clear", "confidence": 1.5,
                "evidence": "x", "unknown_reason": "",
            })

    def test_review_requires_an_explicit_candidate_zone(self):
        with self.assertRaisesRegex(ValueError, "candidate zone"):
            review_chart_with_vision(b"image", "test-key")

    def test_reference_is_loaded_from_repository(self):
        reference = load_strategy_reference()
        self.assertIn("9–10", reference)
        self.assertIn("زيارة", reference)


if __name__ == "__main__":
    unittest.main()
