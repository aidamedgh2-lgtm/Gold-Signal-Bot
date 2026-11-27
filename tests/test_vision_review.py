import unittest

from services.vision_review import validate_visual_result


class VisionReviewTests(unittest.TestCase):
    def test_valid_visual_result(self):
        result = validate_visual_result({
            "departure": "sharp",
            "approach": "fast",
            "confidence": 0.91,
            "evidence": "Steep departure and rapid return.",
        })
        self.assertEqual(result["departure"], "sharp")
        self.assertEqual(result["approach"], "fast")
        self.assertEqual(result["confidence"], 0.91)

    def test_uncertain_is_a_valid_non_scored_state(self):
        result = validate_visual_result({
            "departure": "uncertain",
            "approach": "uncertain",
            "confidence": 0.2,
            "evidence": "Insufficient visible context.",
        })
        self.assertEqual(result["departure"], "uncertain")

    def test_invalid_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_visual_result({
                "departure": "buy", "approach": "fast",
                "confidence": 0.9, "evidence": "x",
            })

    def test_invalid_confidence_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_visual_result({
                "departure": "sharp", "approach": "fast",
                "confidence": 1.5, "evidence": "x",
            })


if __name__ == "__main__":
    unittest.main()
