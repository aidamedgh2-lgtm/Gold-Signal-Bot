# Strategy contract — original Supply & Demand PDF

Source: user's original 143-page PDF, «المضغوط (1).pdf». See [STRATEGY_REFERENCE.md](STRATEGY_REFERENCE.md), which is injected into the AI vision prompt. The PDF remains authoritative.

## Six criteria (10 points total)

| Criterion | Maximum | Rule |
|---|---:|---|
| Departure shape | 2 | Horizontal/sideways 0; smooth diagonal about 45° = 1; steep/near-vertical about 70–90° = 2 |
| Reward/risk | 2 | Stop beyond departure zone; target at opposing destination reached in prior move. 3:1=2, 2:1=1, 1:1=0 |
| Big picture / MTF | 2 | Start at largest frame and compare same approximate zone on successive smaller frames. 3+ hierarchical matches=2; 2=1; 1=0 |
| Zone visits | 2 | Fresh/unvisited or first return=2; second return=1; third or later=0 |
| Time inside/touching zone | 1 | Count touching/inside candles on D1 and H4; <=4=1; >=5=0 |
| Approach shape | 1 | Fast/rocket-like return=1; diagonal or sideways=0 |

## Decision thresholds
- 9–10: suitable for a pending order only when all six criteria and required price levels are established.
- 7–8: monitor; wait for price action, correction, or retest. 8 is not a pending-order threshold.
- 0–6: no entry under this method.
- Any unknown criterion means no final total or trade recommendation.

## Fidelity constraints
- Departure and approach are separate visual judgments.
- Consecutive candles in one continuous touch are one visit.
- Fresh/unvisited and first return receive 2 visit points.
- Duration counts zone-touching candles, not base-formation candles.
- Do not substitute ATR/OHLC proxies for visual judgments.
- Do not use arbitrary R-multiple targets; the target is the opposing destination reached by the first move.
- Do not impose an M15 confirmation-candle rule absent from the PDF.
- The PDF does not fully specify numerical zone thickness, a universal entry point within the zone, or how to reconcile conflicting D1/H4 duration counts. Mark these unknown.
- No EMA/RSI/ICT rule may replace or veto the six criteria.

## Runtime boundaries
- Twelve Data remains the market-data source; Telegram remains the notification channel.
- No broker order execution.
- GitHub Actions schedules are best-effort, not guaranteed always-on 24/5 monitoring.
- Keep trade signals gated until zone detection and all six criteria pass criterion-level golden-case validation.
