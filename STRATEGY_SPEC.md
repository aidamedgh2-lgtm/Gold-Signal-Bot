# Strategy contract — original Supply & Demand

This file is the governing contract for the rebuild. The original 143-page
strategy PDF remains the source of truth; this document records the agreed
six-part score and explicitly blocks silent substitution by EMA/RSI/ICT rules.

## Required score (10 points)

| Criterion | Maximum | Rule |
|---|---:|---|
| Departure strength | 2 | Visual classification: sideways=0, diagonal=1, sharp/near-vertical=2 |
| Reward/risk | 2 | Stop beyond the departure zone; target at the prior opposing destination; 3:1=2, 2:1=1, 1:1=0 |
| Higher-timeframe context | 2 | Hierarchical alignment across at least three timeframes=2 |
| Zone visits | 2 | First return=2, second=1, third or later=0 |
| Time in zone | 1 | Four candles or fewer=1; five or more=0, subject to the PDF's D1/H4 counting instructions |
| Approach to zone | 1 | Fast/strong approach=1; diagonal or sideways=0 |

## Fidelity constraints

- Departure strength and approach shape are separate observations.
- Consecutive candles touching a zone during one continuous return are one visit.
- Do not present ATR/OHLC proxies as equivalent to the PDF's visual judgments.
- Where a visual judgment cannot be established from available data, mark it
  as unknown and do not invent a score.
- The exact treatment of an 8/10 score and any ambiguous counting detail must
  be resolved against the PDF before final signal policy is enabled.
- No EMA/RSI/ICT condition may replace or veto the original six criteria.
- The hybrid layer may assist zone discovery and validation only after
  criterion-level fidelity is demonstrated.

## Runtime boundaries

- Market data remains supplied by the existing Twelve Data integration.
- Notifications remain supplied by the existing Telegram bot integration.
- Secrets remain in GitHub Actions repository secrets; never commit credentials.
- The first release is alert-only. It must never submit broker orders.
- Intended monitoring is 24/5, but GitHub Actions schedules are best-effort;
  do not describe them as guaranteed real-time operation.

## Acceptance gates

1. Unit tests for deterministic calculations and service adapters.
2. Golden-case comparison against manually scored examples from the PDF.
3. Criterion-by-criterion agreement report; visual proxies must be labelled.
4. Historical test with realistic spread/slippage and adequate sample size.
5. Demo/paper forward test before any live reliance.
6. Do not merge or enable automated trade execution merely because syntax
   checks or unit tests pass.
