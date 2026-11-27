# Historical backtest gate — 2026-11-27

## Status: BLOCKED — no strategy-valid performance result

The chart-first AI detector is now wired into the live observation path, but it is
not yet validated as a zone-boundary detector. The current PDF golden set contains
manual pixel annotations and qualitative labels; it does not contain independently
verified price/time boundaries for all examples. A successful unit test of JSON
validation is not evidence that the vision model reads zones correctly.

A historical P/L backtest is deliberately not run from the former ATR/OHLC proxy.
That proxy was previously shown to deviate from the PDF strategy, and its prior
negative result is not a valid test of this visual method.

## Required evidence before a valid replay

1. Commit actual chart-image crops for the PDF cases and have a second reviewer
   verify each zone polygon, timeframe, departure label, and approach label.
2. Add historical chart-image fixtures with calibrated axes and human-verified
   zone price/time bounds. Ambiguous PDF pages remain excluded from scoring.
3. Run the exact pinned vision model against those fixtures; report per-label
   precision/recall and boundary error. Model confidence is not accuracy.
4. Establish a no-lookahead chronological replay: each decision may see only
   candles available at that timestamp. Freeze model/version and prompt.
5. Resolve from the PDF (or leave explicitly unresolved) the entry price within
   the zone and any missing target/stop details. Do not choose a convenient
   midpoint or synthetic R multiple.
6. Use broker-matched XAU/USD history, spread and slippage; report sample size,
   win rate, profit factor, expectancy in R, max drawdown, and out-of-sample
   results. Twelve Data spot OHLC is not HFM execution data.

## Current runtime safety

The bot sends only preliminary visual observations. It does not calculate a
complete /10 score, issue a pending-order recommendation, or execute broker
orders. Any unclear zone boundary or failed AI call produces no candidate.
