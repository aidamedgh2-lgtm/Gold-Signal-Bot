# Gold Signal Bot

A first-version, alert-only XAU/USD technical-analysis bot. It does **not** connect to a broker account and cannot place trades.

## What it checks

- H4: EMA 50 / EMA 200 trend alignment
- H1: EMA 50 / EMA 200 confirmation
- M15: close relative to EMA 50 and RSI(14)
- ATR(14): indicative stop-loss and target distances
- Sends BUY or SELL only when all initial conditions align; otherwise sends nothing (NO TRADE).

This is a basic prototype, not a validated profitable strategy. It does not yet include news filtering, support/resistance validation, spread checks, or historical backtesting.

## Important market-data limitation

The configured source is Twelve Data, symbol `XAU/USD`. Its quote and candles may differ from HFM's XAUUSD feed because providers can differ in liquidity, timestamps, spreads, and price construction. Compare the feed with your HFM MT5 chart before relying on any alert. Spot gold has no consolidated exchange volume; this bot does not use volume.

The script requests 4-hour, 1-hour, and 15-minute candles and excludes the newest returned candle to reduce the risk of analyzing an unfinished bar. If data is missing, insufficient, or the API returns an error, the run stops rather than inventing a signal.

## Setup

Create these GitHub Actions repository secrets (Settings → Secrets and variables → Actions → New repository secret):

- `TWELVEDATA_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not put secret values in source files, issues, or chat messages.

Then open Actions → **Gold signal checks** → **Run workflow** for a manual test. The workflow is also scheduled every 15 minutes. GitHub scheduled workflows are best-effort and can run late; this is not a real-time or 24/7 execution guarantee.

## Telegram

The bot must already have been created with Telegram's BotFather. Send a message to your bot first, then obtain the chat ID using Telegram's bot updates endpoint or an appropriate bot-management method. Keep both token and chat ID private.

## Risk notice

Alerts are for paper testing only. Entry, stop, and targets are calculated from provider candles and ATR; they are not broker-executable prices. Do not trade real money based on this prototype. Validate the data feed, test signals over historical data, and forward-test on a demo account first.
