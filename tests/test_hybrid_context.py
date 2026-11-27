import unittest

from hybrid_context import (
    confirmed_swings, market_structure, liquidity_sweep,
    fair_value_gaps, momentum_state, evaluate_context,
)


def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


class HybridContextTests(unittest.TestCase):
    def test_swing_is_not_confirmed_until_right_bars_exist(self):
        bars = [bar(10, 11, 9, 10), bar(10, 12, 9, 11),
                bar(11, 15, 10, 12), bar(12, 13, 10, 11),
                bar(11, 12, 8, 9)]
        early = confirmed_swings(bars[:4], left=1, right=2)
        complete = confirmed_swings(bars, left=1, right=2)
        self.assertEqual(early["highs"], [])
        self.assertEqual(complete["highs"][-1]["price"], 15)

    def test_equal_highs_are_not_arbitrarily_called_a_pivot(self):
        bars = [bar(10, 12, 9, 10), bar(10, 12, 9, 11),
                bar(11, 11, 8, 9)]
        self.assertEqual(confirmed_swings(bars, 1, 1)["highs"], [])

    def test_bullish_fvg_uses_three_closed_candles(self):
        bars = [bar(10, 11, 9, 10), bar(11, 14, 10, 13),
                bar(13, 15, 12, 14)]
        gaps = fair_value_gaps(bars)
        self.assertEqual(gaps[-1]["direction"], "bullish")
        self.assertEqual((gaps[-1]["low"], gaps[-1]["high"]), (11, 12))

    def test_bearish_fvg(self):
        bars = [bar(14, 15, 13, 14), bar(13, 14, 10, 11),
                bar(11, 12, 9, 10)]
        self.assertEqual(fair_value_gaps(bars)[-1]["direction"], "bearish")

    def test_momentum_is_descriptive_not_a_trade_signal(self):
        result = momentum_state([bar(10, 15, 9, 14)])
        self.assertEqual(result["direction"], "bullish")
        self.assertAlmostEqual(result["body_fraction"], 4 / 6)

    def test_invalid_ohlc_is_rejected(self):
        self.assertEqual(fair_value_gaps([bar(10, 9, 8, 10)]), [])

    def test_context_requires_explicit_trade_direction(self):
        with self.assertRaises(ValueError):
            evaluate_context([bar(10, 11, 9, 10)], "LONG")


if __name__ == "__main__":
    unittest.main()
