# Gold Signal Bot

A first-version, alert-only XAU/USD technical-analysis bot. It does **not** connect to a broker account and cannot place trades.

## What it checks

- H4: EMA 50 / EMA 200 trend alignment
- H1: EMA 50 / EMA 200 confirmation
- M15: EMA 50, RSI(14), confirmed swing structure (higher highs/higher lows or lower highs/lower lows), and a close beyond the previous candle high/low
- ATR(14): indicative stop-loss and three target distances (TP1/TP2/TP3)
- Sends BUY or SELL only when H4/H1 trend, M15 structure, candle trigger, and RSI conditions align; otherwise sends nothing (NO TRADE).

This remains an experimental prototype, not a validated profitable strategy. Swing-structure confirmation is a simple rule-based filter and is not a full market-structure/BOS/CHOCH model. It does not yet include news filtering, economic-calendar data, validated support/resistance zones, broker spread checks, Elliott-wave analysis, session statistics, Bookmap/order-flow data, or historical backtesting.

## Important market-data limitation

The configured source is Twelve Data, symbol `XAU/USD`. Its quote and candles may differ from HFM's XAUUSD feed because providers can differ in liquidity, timestamps, spreads, and price construction. Compare the feed with your HFM MT5 chart before relying on any alert. Spot gold has no consolidated exchange volume; this bot does not use volume.

The script requests 4-hour, 1-hour, and 15-minute candles and excludes the newest returned candle to reduce the risk of analyzing an unfinished bar. If data is missing, insufficient, or the API returns an error, the run stops rather than inventing a signal.

## Setup

Create these GitHub Actions repository secrets (Settings → Secrets and variables → Actions → New repository secret):

- `TWELVEDATA_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not put secret values in source files, issues, or chat messages.

Then open Actions → **Gold signal checks** → **Run workflow**. Select `test_telegram=true` only to send a Telegram connectivity test; that run will not execute market analysis. Leave it false for a normal analysis run, which first checks Python syntax. The workflow is also scheduled every 15 minutes. GitHub scheduled workflows are best-effort and can run late; this is not a real-time or 24/7 execution guarantee.

## Telegram

The bot must already have been created with Telegram's BotFather. Send a message to your bot first, then obtain the chat ID using Telegram's bot updates endpoint or an appropriate bot-management method. Keep both token and chat ID private.

## Risk notice

Alerts are for paper testing only. Entry, stop, and targets are calculated from provider candles and ATR; they are not broker-executable prices. Do not trade real money based on this prototype. Validate the data feed, test signals over historical data, and forward-test on a demo account first.


## Historical strategy comparison (manual, paper research only)

Open Actions → **Gold signal checks** → **Run workflow** and set
`run_backtest=true` (leave `test_telegram=false`). This runs `backtest.py`
without sending a Telegram trade alert or changing the live bot's signal state.
The run downloads a selectable historical window (90, 180, 365, or 730 days)
from Twelve Data in pages of up to 5,000 M15 candles. Requests are spaced to
reduce the risk of exceeding free-tier rate limits. If the provider cannot
supply the full requested window, the backtest stops with an explicit error
rather than silently presenting a shorter sample as complete. It creates
`summary.json` and `trades.csv` as the **gold-strategy-backtest** workflow
artifact. Download the artifact from that workflow run.

The comparison evaluates the current Technical rules and a deliberately
simplified, OHLC-based ICT proxy separately, and records the actual candle
count, requested days, and API request count in `summary.json`. Entries are modeled at the next
M15 candle open; a 2R target, 48-bar maximum holding period, and conservative
stop-first handling are used. Results omit spread, slippage, commissions,
swaps, and HFM feed differences. The available history may be too short for
statistical conclusions, especially for higher-timeframe EMA warm-up. Treat
this as an initial diagnostic, not proof of profitability or a basis for live
trading. The scheduled bot continues its normal alert-only workflow.


## PDF strategy visual replay (research only)

The separate **PDF strategy visual historical replay** workflow reviews chronological chart snapshots on MN1, W1, D1, H4, H1 and M15. It requires the GitHub Actions secrets TWELVEDATA_API_KEY and GEMINI_API_KEY. The default run is 90 days with 6 checkpoints; the workflow fetches additional pre-window history for higher-timeframe context and uses closed candles only.

The replay records visual zone candidates, a second AI review, hierarchical timeframe matches, visit counts, and D1/H4 zone-touch counts. It deliberately does **not** invent the PDF's missing planned entry, stop, or opposing target. Therefore it does not issue a final /10 score or a trade signal. A successful workflow means the visual replay completed, not that the strategy is profitable or fully validated. Inspect the uploaded JSON/CSV evidence and the unresolved criteria before drawing conclusions.
