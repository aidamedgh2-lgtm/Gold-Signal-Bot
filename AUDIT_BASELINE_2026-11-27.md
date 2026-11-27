# Baseline compliance audit — historical validation start

Audit date: 2026-11-27
Repository: `aidamedgh2-lgtm/Gold-Signal-Bot`
Reviewed branch: `ai/vision-chart-review-v1`
Review scope: `supply_demand_live.py`, `strategy_fidelity.py`, `services/vision_review.py`, `STRATEGY_REFERENCE.md`, `STRATEGY_SPEC.md`, `AI_AUDIT_CONTRACT.md`, current unit tests and `backtest.py`.
Source inspected: user's original 143-page PDF, especially printed pages 32–35, 67–76, 135–143. PDF page numbers below are the printed PDF page numbers.

## RESULT

`NON_COMPLIANT` for the current zone engine. The visual-review component is only a partial observation layer. The system is not eligible for strategy backtesting as a faithful implementation yet. No profitability conclusion is drawn.

## Blocking findings

| Severity | Rule | Evidence in code | Finding | Required correction |
|---|---|---|---|---|
| BLOCKER | Zone identification must follow the PDF's visual zone drawing and multi-timeframe examples | `supply_demand_live.py::detect_zones` | Candidate zones are generated from short bases, ATR range thresholds, and OHLC body/wick formulas. AI is shown a shaded zone created by that heuristic; it is explicitly not independently locating the PDF zone. | Keep this detector out of the strategy-validation path. Build chart-first zone annotation/recognition and compare against manually labelled PDF examples. Do not invent numeric zone thickness where the PDF is silent. |
| BLOCKER | Departure shape is a visual 0/1/2 judgment | `detect_zones` computes `move_atr`, `impulse_share`, `ROCKET_ATR`, `STAIR_ATR`; later score uses `move_points` | ATR thresholds decide the departure class before AI review. This is a direct substitute for the visual angle/shape criterion described on PDF pp. 33–35 and the examples on pp. 67–70. | AI or a human label must classify the visible geometry; numeric proxy cannot assign the criterion score. |
| BLOCKER | Duration counts candles touching/inside the zone, not base candles | `detect_zones`: `duration_points = 1 if count <= 4`; `base_bars = count` | The live detector scores the number of base-formation candles as duration. This is not the PDF duration criterion. | Count the zone-touching candles on D1 and H4 over the relevant historical zone life. If the two interpretations disagree and source context does not resolve it, mark unknown. |
| BLOCKER | Approach criterion evaluates the complete return path visually | `detect_zones`: `fast_approach` based on ATR distance, three candles and last candle direction | ATR distance plus a single candle direction is used as a visual fast-return substitute. The PDF pp. 135–141 describes the return shape and specifically illustrates a 7/8-like path; no numeric formula is supplied. | Provide the complete return path to AI Vision and require evidence/uncertainty. No ATR-derived point. |
| BLOCKER | R:R target is the opposing destination reached in the prior move; entry must be established | `detect_zones`: midpoint entry, ATR-buffer stop, max/min of a rolling 100-bar lookback | Entry is forced to zone midpoint; stop uses ATR buffer; target is a generic 100-bar extreme. None is guaranteed to be the PDF's source-defined level. | Label source-based origin zone, planned entry and opposing destination from chart context. If any is not identifiable, R:R remains unresolved. |
| BLOCKER | MTF requires the same approximate zone, top-down hierarchical matching | `main` matches zones using `overlaps` and a tolerance involving ATR; counts distinct frames | The matcher uses ATR-derived tolerance and does not establish that the same visually identified zone/characteristics are matched. The pure helper `hierarchical_mtf_points` also only counts distinct ordered frame labels and does not itself verify zone identity. | Match labelled zone identity/characteristics from largest available timeframe downward; preserve allowed skips only where the source shows no suitable zone. |
| MAJOR | AI audit must review full code and evidence, not just a candidate chart | `services/vision_review.py::review_chart_with_vision` | Current OpenAI call is a visual classifier. It receives extracted text and a chart crop; it does not read repository source files, test traces, or the original PDF binary. | Implement a separate repository compliance audit stage that receives the exact source files, source reference and golden-case results, then returns evidence-linked findings. |
| MAJOR | PDF illustrations are required for visual fidelity validation | current tests | Unit tests validate arithmetic helpers only. No labelled chart-image benchmark or live API visual smoke test is present. | Add the golden-case benchmark described in `GOLDEN_CASES.md`; keep visual model results separate from deterministic unit tests. |
| MAJOR | No extra entry confirmation unless source requires it | `confirmation()` and legacy code after the early return in `main()` | A universal M15 engulfing/strong-close confirmation exists in the legacy path. Current `main()` returns after candidate visual review, so this path is currently unreachable, but it must not be re-enabled as a PDF rule. | Keep it disabled unless a specific PDF passage supports the rule. |
| INFO | Existing strategy scoring helper | `strategy_fidelity.py` | RR, visits, duration and unknown-handling primitives have tests, but their correctness does not validate the detector or the end-to-end engine. | Retain as isolated primitives only; extend with source-labelled integration cases. |

## Source evidence inspected

- PDF p. 32: score bands: 9–10 pending order, 7–8 monitor, below 7 reject (the source wording is reproduced in the source page).
- PDF pp. 33–35: departure-shape scale: horizontal 0–30° = 0; smooth diagonal around 45° = 1; steep/near-vertical = 2.
- PDF pp. 67–76: find the strong fast movement, draw and compare the zone from the largest timeframe downward; the source explicitly allows moving to weekly/daily when the larger frame has no suitable zone, and scores three matching zones = 2, two = 1, fewer = 0.
- PDF pp. 135–141: evaluate the return to the zone as rocket-like versus diagonal/horizontal; p. 141 gives a 7/8-like visual analogy, not a numeric formula.
- PDF p. 143: confirms the six criterion weights (2+2+2+2+1+1).

The extracted `STRATEGY_REFERENCE.md` remains a working transcription; the original PDF remains authoritative.

## Historical test gate

Do not run or interpret a P&L backtest as a test of this strategy until the blocking detector and criterion defects are addressed and golden visual cases are labelled. Otherwise the result measures the current OHLC/ATR proxy, not the user's PDF strategy.

After the fidelity gate:
1. Use historical XAU/USD data with explicit provider, date range, timezone and missing-bar checks.
2. Replay chronologically with no look-ahead: a zone can only be used after it is identifiable from candles available at that time.
3. Apply the PDF's six criteria only; unresolved criteria suppress the score and signal.
4. Model spread, slippage and commissions using documented assumptions; state if the feed is not HFM.
5. Split development and untouched out-of-sample periods.
6. Report trade count, win rate, profit factor, expectancy in R, max drawdown, and data limitations.
7. Paper-forward test before enabling Telegram trade signals.

## Limitations

- No numerical zone-boundary rule is specified sufficiently by the source to justify a fabricated OHLC/ATR replacement.
- PDF screenshots are visual examples, not a labelled machine-readable XAU/USD candle dataset.
- The original PDF was inspected for the cited pages, but the repository's AI runtime currently receives only extracted text, not the PDF binary or page images.
- No live OpenAI API smoke test or new historical P&L run was performed in this baseline audit.
- This branch adds documentation only. It does not alter runtime behaviour, enable trading, or merge any pull request.
