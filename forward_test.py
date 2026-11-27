"""Independent 90-day forward paper test: legacy ICT proxy vs ICT + Fibonacci Classic.
No Telegram messages and no live orders. Closed M15 Twelve Data candles only.
Gross R only: broker spread, slippage, commission and swap are not modeled.
"""
import json, math, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://api.twelvedata.com/time_series"
STATE_FILE = Path("forward_test_state_v2.json")
TEST_DAYS = 90
STRATEGY_VERSION = "legacy-ict-proxy-v2__fib-classic-v1__causal-fvg__entry-bar-exits__next-open__2R__48bars"
FIB_LEVELS = (0.382, 0.500, 0.618, 0.705, 0.786)


def fetch_closed_m15():
    params = urllib.parse.urlencode({
        "symbol": "XAU/USD", "interval": "15min", "outputsize": 260,
        "timezone": "UTC", "apikey": os.environ["TWELVEDATA_API_KEY"], "format": "JSON",
    })
    req = urllib.request.Request(BASE_URL + "?" + params, headers={"User-Agent": "Gold-Forward-Paper-Test/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "values" not in payload:
        raise RuntimeError("Twelve Data error: " + str(payload.get("message") or payload))
    bars = [{"time": x["datetime"], **{k: float(x[k]) for k in ("open", "high", "low", "close")}} for x in payload["values"]]
    bars.sort(key=lambda x: x["time"])
    if len(bars) > 1:
        bars = bars[:-1]
    if len(bars) < 205:
        raise RuntimeError("Insufficient closed M15 history: " + str(len(bars)))
    for b in bars:
        if not all(math.isfinite(b[k]) for k in ("open", "high", "low", "close")):
            raise RuntimeError("Non-finite OHLC value; refusing to process data")
        if b["high"] < max(b["open"], b["close"], b["low"]) or b["low"] > min(b["open"], b["close"], b["high"]):
            raise RuntimeError("Invalid OHLC candle; refusing to process data")
    return bars


def market_structure(candles, lookback=2, scan=80):
    window = candles[-(scan + 2 * lookback + 1):]
    highs, lows = [], []
    for i in range(lookback, len(window) - lookback):
        h, l = window[i]["high"], window[i]["low"]
        neighbors = window[i-lookback:i] + window[i+1:i+lookback+1]
        if all(h > x["high"] for x in neighbors): highs.append(h)
        if all(l < x["low"] for x in neighbors): lows.append(l)
    return {"last_swing_high": highs[-1] if highs else None, "last_swing_low": lows[-1] if lows else None}


def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs = []
    for i in range(1, len(candles)):
        b, prev = candles[i], candles[i-1]["close"]
        trs.append(max(b["high"]-b["low"], abs(b["high"]-prev), abs(b["low"]-prev)))
    value = sum(trs[:period]) / period
    for tr in trs[period:]: value = ((period-1)*value + tr) / period
    return value


def live_ict_candidate(candles, current_atr):
    """Faithful copy of bot.py ict_candidate; input ends at the signal candle."""
    if len(candles) < 100 or not current_atr or current_atr <= 0: return None
    prior, recent = candles[:-12], candles[-12:]
    structure = market_structure(prior, lookback=2, scan=80)
    swing_high, swing_low = structure["last_swing_high"], structure["last_swing_low"]
    if swing_high is None or swing_low is None: return None
    bull_sweep = bear_sweep = None
    for i, candle in enumerate(recent):
        if candle["low"] < swing_low and candle["close"] > swing_low: bull_sweep = (i, candle["low"])
        if candle["high"] > swing_high and candle["close"] < swing_high: bear_sweep = (i, candle["high"])
    candidates = []
    for direction, sweep, mss_level in (
        ("BUY", bull_sweep, max(x["high"] for x in prior[-8:])),
        ("SELL", bear_sweep, min(x["low"] for x in prior[-8:])),
    ):
        if sweep is None: continue
        sweep_i, extreme = sweep
        post = recent[sweep_i+1:]
        if not post: continue
        mss = any(x["close"] > mss_level for x in post) if direction == "BUY" else any(x["close"] < mss_level for x in post)
        if not mss: continue
        fvg = None
        for j in range(max(sweep_i+3, len(recent)-6), len(recent)):
            absolute = len(candles)-12+j
            if absolute < 2: continue
            first, third = candles[absolute-2], candles[absolute]
            if direction == "BUY" and third["low"] > first["high"]: fvg = (first["high"], third["low"])
            elif direction == "SELL" and third["high"] < first["low"]: fvg = (third["high"], first["low"])
        if fvg is None: continue
        zlo, zhi = min(fvg), max(fvg)
        entry = (zlo+zhi)/2
        if abs(candles[-1]["close"]-entry) > 1.5*current_atr: continue
        stop = extreme-.20*current_atr if direction == "BUY" else extreme+.20*current_atr
        risk = abs(entry-stop)
        if risk <= 0 or risk > 2.5*current_atr: continue
        candidates.append({"direction": direction, "entry": entry, "stop": stop, "risk": risk})
    if len({x["direction"] for x in candidates}) > 1:
        return None  # Conflicting BUY and SELL candidates are not actionable.
    return candidates[-1] if candidates else None


def swing_points(bars, lookback=3):
    highs, lows = [], []
    for i in range(lookback, len(bars)-lookback):
        h, l = bars[i]["high"], bars[i]["low"]
        neighbors = list(range(i-lookback, i)) + list(range(i+1, i+lookback+1))
        if all(h > bars[j]["high"] for j in neighbors): highs.append((i, h))
        if all(l < bars[j]["low"] for j in neighbors): lows.append((i, l))
    return highs, lows


def fibonacci_classic_near(bars, direction, lookback=3, scan=80):
    start = max(0, len(bars)-1-scan-2*lookback)
    window = bars[start:]
    highs, lows = swing_points(window, lookback)
    if direction == "BUY":
        pairs = [(lo, hi) for lo in lows for hi in highs if lo[0] < hi[0]]
        if not pairs: return False
        lo, hi = max(pairs, key=lambda p: p[1][0])
        low, high = lo[1], hi[1]
        levels = {r: high-(high-low)*r for r in FIB_LEVELS}
    elif direction == "SELL":
        pairs = [(hi, lo) for hi in highs for lo in lows if hi[0] < lo[0]]
        if not pairs: return False
        hi, lo = max(pairs, key=lambda p: p[1][0])
        high, low = hi[1], lo[1]
        levels = {r: low+(high-low)*r for r in FIB_LEVELS}
    else: return False
    if high <= low: return False
    trs = []
    for j in range(max(1, len(window)-14), len(window)):
        b, prev = window[j], window[j-1]["close"]
        trs.append(max(b["high"]-b["low"], abs(b["high"]-prev), abs(b["low"]-prev)))
    if not trs: return False
    tolerance = .15*(sum(trs)/len(trs))
    price = window[-1]["close"]
    return any(abs(price-levels[r]) <= tolerance for r in (.382, .500, .618, .786))


def load_state():
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else None


def save_state(state):
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE_FILE)


def metrics(trades):
    vals = [x["r"] for x in trades]
    wins, losses = [x for x in vals if x > 0], [x for x in vals if x < 0]
    loss_sum = abs(sum(losses))
    return {"trades": len(vals), "win_rate_pct": round(100*len(wins)/len(vals), 2) if vals else 0.0,
            "profit_factor": round(sum(wins)/loss_sum, 3) if loss_sum else (None if not wins else "inf"),
            "gross_net_R": round(sum(vals), 3), "expectancy_R": round(sum(vals)/len(vals), 3) if vals else 0.0}


def _close_book_position(book, bar, index):
    """Apply stop-first OHLC exits, including the candle in which entry occurred."""
    active = book.get("active")
    if not active:
        return False
    direction, stop, risk = active["direction"], active["stop"], active["risk"]
    target = active["entry"] + 2 * risk if direction == "BUY" else active["entry"] - 2 * risk
    hit_stop = bar["low"] <= stop if direction == "BUY" else bar["high"] >= stop
    hit_target = bar["high"] >= target if direction == "BUY" else bar["low"] <= target
    age = index - active["entry_index"]
    if not (hit_stop or hit_target or age >= 48):
        return False
    if hit_stop:
        result, reason = -1.0, "stop"
    elif hit_target:
        result, reason = 2.0, "target"
    else:
        result = ((bar["close"] - active["entry"]) / risk if direction == "BUY"
                  else (active["entry"] - bar["close"]) / risk)
        reason = "timeout"
    book["trades"].append({
        "signal_time": active["signal_time"],
        "entry_time": active["entry_time"],
        "exit_time": bar["time"],
        "direction": direction,
        "entry": active["entry"],
        "stop": stop,
        "r": round(result, 6),
        "exit_reason": reason,
    })
    book["active"] = None
    return True


def process_bar(state, bars, i):
    bar = bars[i]
    for name in ("ICT", "ICT + Fibonacci Classic"):
        book = state["books"][name]
        had_active = book.get("active") is not None
        if had_active:
            _close_book_position(book, bar, i)
            # Do not re-enter on a candle that was managing an older position.
            continue

        bar_open_time = datetime.strptime(bar["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if bar_open_time < datetime.fromisoformat(state["test_start_utc"]):
            continue
        prefix = bars[:i]
        signal_atr = atr(prefix)
        if signal_atr is None:
            continue
        signal = live_ict_candidate(prefix, signal_atr)
        if signal is None:
            continue
        if name == "ICT + Fibonacci Classic" and not fibonacci_classic_near(prefix, signal["direction"]):
            continue

        entry = bar["open"]
        stop = signal["stop"]
        direction = signal["direction"]
        # A gap through the stop invalidates the entry; do not use absolute risk alone.
        if (direction == "BUY" and entry <= stop) or (direction == "SELL" and entry >= stop):
            continue
        risk = abs(entry - stop)
        if risk <= 0 or risk > 4 * signal["risk"]:
            continue
        book["active"] = {
            "signal_time": prefix[-1]["time"],
            "entry_time": bar["time"],
            "entry_index": i,
            "entry": entry,
            "direction": direction,
            "stop": stop,
            "risk": risk,
        }
        # The entry candle may already have reached SL or TP.
        _close_book_position(book, bar, i)


def main():
    bars = fetch_closed_m15()
    state = load_state()
    now = datetime.now(timezone.utc)
    if state is None:
        state = {
            "test_start_utc": now.isoformat(),
            "test_end_utc": (now + timedelta(days=TEST_DAYS)).isoformat(),
            "strategy_version": STRATEGY_VERSION,
            "feed": "XAU/USD Spot - Twelve Data",
            "timeframe": "M15",
            "last_processed_candle": bars[-1]["time"],
            "processed_candles": 0,
            "books": {
                "ICT": {"active": None, "trades": []},
                "ICT + Fibonacci Classic": {"active": None, "trades": []},
            },
        }
        save_state(state)
        print(json.dumps({
            "status": "initialized",
            "start": state["test_start_utc"],
            "end": state["test_end_utc"],
            "note": "New v2 paper-test baseline; previous v1 state is preserved separately.",
        }, indent=2))
        return

    if state.get("strategy_version") != STRATEGY_VERSION:
        raise RuntimeError("Strategy version mismatch; refusing to mix results.")

    times = [b["time"] for b in bars]
    last = state["last_processed_candle"]
    if last not in times:
        raise RuntimeError("Last processed candle outside rolling window; stopping rather than skipping data.")

    # Rebase persisted open-position indices to this run's rolling candle window.
    for book in state["books"].values():
        active = book.get("active")
        if active:
            if active["entry_time"] not in times:
                raise RuntimeError("An open paper position is outside the rolling candle window; refusing inaccurate duration tracking.")
            active["entry_index"] = times.index(active["entry_time"])

    end_dt = datetime.fromisoformat(state["test_end_utc"])
    start_i = times.index(last) + 1
    processed_this_run = 0
    for i in range(start_i, len(bars)):
        candle_dt = datetime.strptime(bars[i]["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if candle_dt >= end_dt:
            break
        process_bar(state, bars, i)
        state["last_processed_candle"] = bars[i]["time"]
        state["processed_candles"] += 1
        processed_this_run += 1

    if now >= end_dt:
        eligible = [
            i for i, stamp in enumerate(times)
            if datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) < end_dt
        ]
        if not eligible:
            raise RuntimeError("No closed candle is available before the configured test end.")
        final_bar = bars[eligible[-1]]
        for book in state["books"].values():
            active = book.get("active")
            if active:
                risk = active["risk"]
                result_r = ((final_bar["close"] - active["entry"]) / risk
                            if active["direction"] == "BUY"
                            else (active["entry"] - final_bar["close"]) / risk)
                book["trades"].append({
                    "signal_time": active["signal_time"],
                    "entry_time": active["entry_time"],
                    "exit_time": final_bar["time"],
                    "direction": active["direction"],
                    "entry": active["entry"],
                    "stop": active["stop"],
                    "r": round(result_r, 6),
                    "exit_reason": "test_end",
                })
                book["active"] = None
        state["last_processed_candle"] = final_bar["time"]
        state["completed_utc"] = now.isoformat()
        save_state(state)
        print("90-day v2 test period ended; remaining paper positions were marked to the last closed candle before test end.")
        print(json.dumps({k: metrics(v["trades"]) for k, v in state["books"].items()}, ensure_ascii=False, indent=2))
        return

    if processed_this_run == 0:
        print("No new eligible closed M15 candle.")
        return

    save_state(state)
    result = {
        "test_start_utc": state["test_start_utc"],
        "test_end_utc": state["test_end_utc"],
        "last_processed_candle": state["last_processed_candle"],
        "new_candles": processed_this_run,
        "processed_candles_total": state["processed_candles"],
        "strategies": {k: metrics(v["trades"]) for k, v in state["books"].items()},
        "open_positions": {k: bool(v["active"]) for k, v in state["books"].items()},
        "warning": "Gross R only; spread, slippage, commission, swap and HFM feed differences excluded.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("# Gold legacy ICT forward paper test v2\n\n**90 days | Virtual trades only | Gross R (costs excluded)**\n\n")
            f.write("| Strategy | Trades | Win rate | Profit factor | Gross net R |\n|---|---:|---:|---:|---:|\n")
            for k, m in result["strategies"].items():
                f.write("| {} | {} | {}% | {} | {} |\n".format(k, m["trades"], m["win_rate_pct"], m["profit_factor"], m["gross_net_R"]))
            f.write("\nLast processed candle (UTC): {}\n\n".format(state["last_processed_candle"]))
            f.write("Twelve Data Spot may differ from HFM. Trading costs are excluded.\n")


if __name__ == "__main__":
    main()
