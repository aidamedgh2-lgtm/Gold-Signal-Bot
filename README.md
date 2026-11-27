# Gold Signal Bot

Alert-only experimental project for XAU/USD. It does not connect to a broker account and cannot place orders.

## Current live alert engine

The scheduled **Gold signal checks** workflow runs `supply_demand_live.py` every 15 minutes.

The live engine currently:
- Downloads MN1, W1, D1, H4, H1 and M15 candles from Twelve Data for `XAU/USD`.
- Builds OHLC/ATR-based Supply and Demand zones and scores them out of 10.
- Uses multi-timeframe zone overlap as a confluence factor.
- Sends monitoring messages for scores 7–8.
- Requires a closed M15 confirmation candle (Engulfing or Strong Candle Close) before sending a BUY/SELL alert for scores above 8.
- Does not execute trades.

**Important:** the current live engine still requires M15 confirmation. M1/M5 are not integrated into live signal generation. The `Check M1 and M5 data availability` workflow only checks whether Twelve Data returns those intervals; it is not a strategy test.

## Research scripts are separate from the live engine

- `backtest.py`: historical comparison of legacy Technical and simplified ICT-style rules on M15. It does **not** backtest the current Supply/Demand live engine.
- `forward_test.py`: 90-day forward paper comparison of a legacy ICT OHLC proxy against the same proxy with a Fibonacci Classic filter. It does **not** test the current Supply/Demand live engine.
- `bot.py`: an older standalone ICT/Technical prototype. It is not called by the scheduled live workflow.

Do not treat results from these legacy research scripts as evidence that the current Supply/Demand strategy is profitable.

## Data limitations

The configured feed is Twelve Data `XAU/USD` spot. It may differ from HFM's XAUUSD CFD feed in prices, timestamps, spread and candle construction. Spot gold has no single consolidated exchange volume; the Twelve Data M1/M5 access check returned OHLC but no Volume field in the sample.

FinzData GC futures data refers to COMEX Gold futures, not the global XAU/USD spot/CFD market. The live workflow currently sets `FINZDATA_CONTEXT_ENABLED=false`, so COMEX data does not affect live signal scoring or direction.

## Setup

Create these GitHub Actions repository secrets (Settings → Secrets and variables → Actions):
- `TWELVEDATA_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional research/data-check secrets:
- `FINZDATA_API_KEY`
- `GOLDPRICE_API_KEY`

Never place secret values in source files, issues or chat messages.

## Workflows

- **Gold signal checks**: scheduled live analysis; manual Telegram connectivity test; legacy historical backtest; optional COMEX data check.
- **Check M1 and M5 data availability**: data access only, not strategy performance.
- **Gold legacy ICT forward paper test**: virtual legacy ICT-proxy research only; no Telegram trade messages and no broker orders.
- **Validate bot code**: compiles all Python scripts and runs offline regression tests.

GitHub scheduled workflows are best-effort and may run late. They are not a real-time or 24/7 execution guarantee.

## Risk notice

All signals and research outputs are experimental. Backtests and forward paper tests may omit spread, slippage, commissions, swaps and differences from HFM execution. Do not trade real money based on this project. Validate the data feed, test the exact live strategy on adequate historical data, include realistic costs, and forward-test on a demo account first.
