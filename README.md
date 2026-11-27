# Gold Signal Bot — clean rebuild track

The clean rebuild is governed by [STRATEGY_SPEC.md](STRATEGY_SPEC.md).
The original Supply & Demand method is the authority; experimental EMA/RSI/ICT
systems are not the active strategy.

## Preserved integrations

- **Market data:** Twelve Data, XAU/USD, through `services/market_data.py`.
  Existing `TWELVEDATA_API_KEY` secret is retained.
- **Notifications:** Telegram Bot API through `services/telegram.py`.
  Existing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets are retained.
- No broker connection or order execution is included.

## Current status

This branch isolates the existing provider and Telegram adapters from the
strategy engine without changing their service providers or secret names.
The current zone engine is still experimental: several visual criteria are
represented by OHLC/ATR proxies and therefore are **not yet proven faithful**
to the PDF. This branch is a structural cleanup, not a claim of a validated
profitable strategy.

## Required next work

1. Add criterion-level tests and manually scored golden cases from the PDF.
2. Replace unsupported visual guesses with an explicit unknown state.
3. Validate zone detection, scoring, entry, stop and target against the PDF.
4. Backtest and forward-test on suitable data, accounting for costs and feed
   differences.
5. Keep alerts paper-only until all acceptance gates pass.

## Configuration

Set these repository Actions secrets:

- `TWELVEDATA_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Do not paste or commit secret values. The scheduled GitHub Actions workflow is
best-effort and is not a guaranteed always-on 24/5 service.
