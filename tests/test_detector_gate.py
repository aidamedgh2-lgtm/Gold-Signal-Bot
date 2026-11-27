import ast
import unittest
from pathlib import Path


class DetectorSafetyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path("supply_demand_live.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(source)

    def test_legacy_detector_fails_closed(self):
        node = next(n for n in self.tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "detect_zones")
        returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
        self.assertEqual(len(returns), 1)
        self.assertIsInstance(returns[0].value, ast.List)
        self.assertEqual(returns[0].value.elts, [])

    def test_live_main_uses_visual_detector_and_never_scores_trades(self):
        node = next(n for n in self.tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        reachable = []
        for statement in node.body:
            reachable.append(statement)
            if isinstance(statement, ast.Return):
                break
        calls = [n for statement in reachable for n in ast.walk(statement)
                 if isinstance(n, ast.Call)]
        names = [n.func.id for n in calls if isinstance(n.func, ast.Name)]
        self.assertIn("detect_visual_zones", names)
        self.assertIn("assess_candidate", names)
        self.assertNotIn("confirmation", names)
        self.assertNotIn("comex_daily_context", names)
        source = Path("supply_demand_live.py").read_text(encoding="utf-8")
        main_source = source[source.index("def main():"):]
        self.assertIn("لم تُحسب نقاط الاستراتيجية /10", main_source)
        self.assertIn("لا يوجد تنفيذ صفقات", main_source)


if __name__ == "__main__":
    unittest.main()
