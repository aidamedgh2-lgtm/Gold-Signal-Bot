import json
import unittest
from pathlib import Path


class VisualAnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "golden_cases" / "visual_annotations.json"
        cls.data = json.loads(path.read_text(encoding="utf-8"))

    def test_all_annotations_reference_source_pages_and_pixel_bounds(self):
        width = self.data["coordinate_system"]["page_width_px"]
        height = self.data["coordinate_system"]["page_height_px"]
        self.assertGreaterEqual(len(self.data["annotations"]), 8)
        for item in self.data["annotations"]:
            self.assertGreaterEqual(item["source_page"], 1)
            for key in ("zone_bbox_px", "path_bbox_px"):
                bbox = item.get(key)
                if bbox is None:
                    continue
                self.assertEqual(len(bbox), 4)
                x1, y1, x2, y2 = bbox
                self.assertTrue(0 <= x1 < x2 <= width, (item["case_id"], key, bbox))
                self.assertTrue(0 <= y1 < y2 <= height, (item["case_id"], key, bbox))

    def test_ambiguous_timeframe_labels_are_not_silently_resolved(self):
        uncertain = [a for a in self.data["annotations"]
                     if "timeframe_uncertain" in a["status"]]
        self.assertGreaterEqual(len(uncertain), 1)

    def test_approach_schematic_labels_match_source(self):
        cases = {a["case_id"]: a for a in self.data["annotations"]}
        self.assertEqual(cases["PDF-APPROACH-01-FAST"]["expected_points"], 1)
        self.assertEqual(cases["PDF-APPROACH-01-DIAGONAL"]["expected_points"], 0)
        self.assertEqual(cases["PDF-APPROACH-01-GRADUAL"]["expected_points"], 0)


if __name__ == "__main__":
    unittest.main()
