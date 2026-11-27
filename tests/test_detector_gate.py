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

    def test_live_main_stops_before_market_data_or_alerts(self):
        node = next(n for n in self.tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        # The first executable statements must be the hard stop and return.
        self.assertGreaterEqual(len(node.body), 3)
        self.assertIsInstance(node.body[0], ast.Assign)
        self.assertIsInstance(node.body[1], ast.Expr)
        self.assertIsInstance(node.body[1].value, ast.Call)
        self.assertEqual(getattr(node.body[1].value.func, "id", None), "print")
        self.assertIsInstance(node.body[2], ast.Return)


if __name__ == "__main__":
    unittest.main()
