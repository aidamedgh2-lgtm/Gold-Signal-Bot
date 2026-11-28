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

## PDF-grounded AI review and compliance gate

- `AI_AUDIT_CONTRACT.md` is the mandatory instruction set for any AI code/strategy audit. It makes the original PDF the sole authority, prohibits strategy drift and unsupported heuristics, requires evidence for every finding, and blocks claims of full compliance when source or chart evidence is missing.
- AI audit findings must distinguish source fidelity, software correctness, and trading performance. Unknown source rules remain unresolved; they must never be filled by model assumptions.

## PDF-grounded AI vision review

- `STRATEGY_REFERENCE.md` is derived from the original 143-page PDF and is
  loaded into every OpenAI vision request alongside the chart image.
- The model classifies departure and approach shape and reports whether the
  candidate zone is visually readable. It cannot assign a trade score, choose
  direction, or invent entry/stop/target levels.
- The scoring primitives are unit-tested against the PDF's six criteria.
- The runtime remains in candidate-alert mode: it does not yet calculate a
  complete validated /10 score or issue trade recommendations. The PDF does
  not fully specify a numerical zone-thickness algorithm or every entry detail.

## Remaining acceptance work

1. Build manually labelled golden examples from the PDF's chart illustrations.
2. Validate zone boundaries, hierarchical alignment, visits, D1/H4 duration,
   and target/stop placement criterion by criterion.
3. Backtest on broker-matched data with spread/slippage and sufficient sample.
4. Forward-test in paper/demo mode before enabling any signal output.
5. Keep broker execution disabled.

## Configuration

Set these repository Actions secrets:

- `TWELVEDATA_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `OPENAI_API_KEY` (required for AI chart review)
- `OPENAI_VISION_MODEL` (optional; defaults to `gpt-4.1-mini`)

Do not paste or commit secret values. The scheduled GitHub Actions workflow is
best-effort and is not a guaranteed always-on 24/5 service.


## Supply & Demand anchor-zone boundary setting

The zone's price thickness is calculated from the last candle immediately before
the strong move on the higher timeframe. Configure `ZONE_BOUNDARY_MODE`:

- `wick` (default): candle `Low` to `High`, including both wicks.
- `body`: `min(Open, Close)` to `max(Open, Close)`, body only.

The resulting higher-timeframe interval is the reference range for lower-timeframe
zone matching. Lower timeframes must not create a substitute parent range or use
an invented tolerance. Set this environment variable in the bot's runtime
configuration; invalid values fail closed.
