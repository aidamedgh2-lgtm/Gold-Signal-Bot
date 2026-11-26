"""Historical candle-close-only comparison of Technical and ICT-style rules.
Paper research tool: XAU/USD M15 OHLC only; no broker execution or costs modeled.
"""
import csv
import json
import os
import urllib.parse
import urllib.request
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://api.twelvedata.com/time_series"
API_KEY = os.environ["TWELVEDATA_API_KEY"]
OUTPUT = Path("backtest_results")


def fetch_m15(days=None, outputsize=5000):
    """Download a rolling historical window in <=5,000-bar pages."""
    days = int(days or os.getenv("BACKTEST_DAYS", "365"))
    if not 30 <= days <= 730:
        raise ValueError("BACKTEST_DAYS must be between 30 and 730.")
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)
    end_time = now
    collected = {}
    request_count = 0
    max_pages = 20

    while end_time > start_time and request_count < max_pages:
        params = urllib.parse.urlencode({
            "symbol": "XAU/USD",
            "interval": "15min",
            "outputsize": outputsize,
            "timezone": "UTC",
            "order": "desc",
            "end_date": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "apikey": API_KEY,
            "format": "JSON",
        })
        req = urllib.request.Request(
            f"{BASE_URL}?{params}",
            headers={"User-Agent": "Gold-Signal-Backtest/2.0"},
        )
        with urllib.request.urlopen(req, timeout=40) as response:
            payload = json.loads(response.read().decode("utf-8"))
        request_count += 1

        if "values" not in payload:
            raise RuntimeError(
                f"Twelve Data error on page {request_count}: "
                f"{payload.get('message') or payload}"
            )
        values = payload["values"]
        if not values:
            break

        for item in values:
            stamp = datetime.strptime(
                item["datetime"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            if stamp < start_time or stamp + timedelta(minutes=15) > now:
                continue
            collected[item["datetime"]] = {
                "time": item["datetime"],
                **{key: float(item[key]) for key in ("open", "high", "low", "close")},
            }

        oldest = min(
            datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            for item in values
        )
        if oldest <= start_time or len(values) < outputsize:
            break
        next_end = oldest - timedelta(seconds=1)
        if next_end >= end_time:
            raise RuntimeError("Historical pagination made no progress.")
        end_time = next_end
        if request_count < max_pages:
            time.sleep(8.5)

    bars = [collected[key] for key in sorted(collected)]
    if request_count >= max_pages and bars:
        first_time = datetime.strptime(
            bars[0]["time"], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
        if first_time > start_time:
            raise RuntimeError(
                f"Reached the {max_pages}-page safety limit after collecting "
                f"{len(bars)} candles; requested {days} days but coverage is incomplete."
            )
    if len(bars) < 1000:
        raise RuntimeError(
            f"Only {len(bars)} closed M15 candles returned across "
            f"{request_count} requests; need at least 1000."
        )
    print(
        f"Downloaded {len(bars)} closed M15 candles across {request_count} "
        f"requests; requested window: {days} days."
    )
    return bars, request_count


def ema_series(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2 / (period + 1)
    value = sum(values[:period]) / period
    out[period - 1] = value
    for i in range(period, len(values)):
        value = alpha * values[i] + (1 - alpha) * value
        out[i] = value
    return out


def rsi_series(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(x, 0) for x in changes[:period]) / period
    loss = sum(max(-x, 0) for x in changes[:period]) / period
    out[period] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    for i in range(period + 1, len(values)):
        change = changes[i - 1]
        gain = (gain * (period - 1) + max(change, 0)) / period
        loss = (loss * (period - 1) + max(-change, 0)) / period
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def atr_series(bars, period=14):
    out = [None] * len(bars)
    trs = [None]
    for i in range(1, len(bars)):
        b, prev = bars[i], bars[i - 1]["close"]
        trs.append(max(b["high"] - b["low"], abs(b["high"] - prev), abs(b["low"] - prev)))
    if len(bars) <= period:
        return out
    value = sum(trs[1:period + 1]) / period
    out[period] = value
    for i in range(period + 1, len(bars)):
        value = (value * (period - 1) + trs[i]) / period
        out[i] = value
    return out


def aggregate(bars, hours):
    """Build only complete UTC H1/H4 buckets from M15 candles."""
    groups = {}
    for b in bars:
        dt = datetime.strptime(b["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        bucket = int(dt.timestamp()) // (hours * 3600)
        groups.setdefault(bucket, []).append(b)
    result = []
    for bucket, group in groups.items():
        if len(group) == hours * 4:
            bucket_end = datetime.fromtimestamp((bucket + 1) * hours * 3600, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            result.append({"time": bucket_end, "open": group[0]["open"],
                           "high": max(x["high"] for x in group), "low": min(x["low"] for x in group),
                           "close": group[-1]["close"]})
    return result


def swing_points(bars, lookback=3):
    highs, lows = [], []
    for i in range(lookback, len(bars) - lookback):
        h, l = bars[i]["high"], bars[i]["low"]
        neighbors = list(range(i - lookback, i)) + list(range(i + 1, i + lookback + 1))
        if all(h > bars[j]["high"] for j in neighbors):
            highs.append((i, h))
        if all(l < bars[j]["low"] for j in neighbors):
            lows.append((i, l))
    return highs, lows


def structure_label(bars):
    highs, lows = swing_points(bars[-90:], 3)
    if len(highs) < 2 or len(lows) < 2:
        return "unknown"
    hh, hl = highs[-1][1] > highs[-2][1], lows[-1][1] > lows[-2][1]
    lh, ll = highs[-1][1] < highs[-2][1], lows[-1][1] < lows[-2][1]
    return "bull" if hh and hl else "bear" if lh and ll else "range"


def trend_at(bars, index, e50, e200):
    if index < 200 or e50[index] is None or e200[index] is None:
        return None
    close = bars[index]["close"]
    if e50[index] > e200[index] and close > e50[index]:
        return "bull"
    if e50[index] < e200[index] and close < e50[index]:
        return "bear"
    return "neutral"


def build_signals(m15):
    closes = [b["close"] for b in m15]
    e50, e200 = ema_series(closes, 50), ema_series(closes, 200)
    rsi, atr = rsi_series(closes), atr_series(m15)
    h1, h4 = aggregate(m15, 1), aggregate(m15, 4)
    h1c, h4c = [b["close"] for b in h1], [b["close"] for b in h4]
    h1e50, h1e200 = ema_series(h1c, 50), ema_series(h1c, 200)
    h4e50, h4e200 = ema_series(h4c, 50), ema_series(h4c, 200)

    def map_htf(htf, fast, slow):
        mapped, p = [], 0
        for bar in m15:
            while p + 1 < len(htf) and htf[p + 1]["time"] <= bar["time"]:
                p += 1
            mapped.append(trend_at(htf, p, fast, slow) if htf and htf[p]["time"] <= bar["time"] else None)
        return mapped

    h1map, h4map = map_htf(h1, h1e50, h1e200), map_htf(h4, h4e50, h4e200)
    signals = {"Technical": {}, "ICT": {}}
    for i in range(250, len(m15) - 2):
        if atr[i] is None or rsi[i] is None or h1map[i] is None or h4map[i] is None:
            continue
        label = structure_label(m15[max(0, i - 90):i + 1])
        bar = m15[i]
        tech = None
        if h1map[i] == h4map[i] == "bull" and bar["close"] > e50[i] and label == "bull" and bar["close"] > m15[i - 1]["high"] and 50 <= rsi[i] <= 68:
            tech = "BUY"
        elif h1map[i] == h4map[i] == "bear" and bar["close"] < e50[i] and label == "bear" and bar["close"] < m15[i - 1]["low"] and 32 <= rsi[i] <= 50:
            tech = "SELL"
        if tech:
            risk = 1.5 * atr[i]
            signals["Technical"][i] = {"direction": tech, "stop": bar["close"] - risk if tech == "BUY" else bar["close"] + risk, "risk": risk}

        # Explicit ICT-inspired proxy: confirmed swing sweep/reclaim, MSS, then a 3-candle FVG.
        prior = m15[max(0, i - 110):max(0, i - 10)]
        ph, pl = swing_points(prior, 2)
        if not ph or not pl:
            continue
        swing_high, swing_low = ph[-1][1], pl[-1][1]
        window_start = max(0, i - 11)
        window = m15[window_start:i + 1]
        bull_sweep = next((j for j in range(len(window) - 1, -1, -1) if window[j]["low"] < swing_low and window[j]["close"] > swing_low), None)
        bear_sweep = next((j for j in range(len(window) - 1, -1, -1) if window[j]["high"] > swing_high and window[j]["close"] < swing_high), None)
        direction, extreme = None, None
        if bull_sweep is not None:
            sweep_abs = window_start + bull_sweep
            mss_level = max(x["high"] for x in prior[-8:])
            if any(x["close"] > mss_level for x in m15[sweep_abs + 1:i + 1]):
                direction, extreme = "BUY", window[bull_sweep]["low"]
        if bear_sweep is not None:
            sweep_abs = window_start + bear_sweep
            mss_level = min(x["low"] for x in prior[-8:])
            if any(x["close"] < mss_level for x in m15[sweep_abs + 1:i + 1]) and direction is None:
                direction, extreme = "SELL", window[bear_sweep]["high"]
        if direction and i >= 2:
            first, third = m15[i - 2], m15[i]
            fvg = (first["high"], third["low"]) if direction == "BUY" and third["low"] > first["high"] else ((third["high"], first["low"]) if direction == "SELL" and third["high"] < first["low"] else None)
            if fvg:
                zone_mid = sum(fvg) / 2
                stop = extreme - 0.2 * atr[i] if direction == "BUY" else extreme + 0.2 * atr[i]
                risk = abs(zone_mid - stop)
                if abs(bar["close"] - zone_mid) <= 1.5 * atr[i] and 0 < risk <= 2.5 * atr[i]:
                    signals["ICT"][i] = {"direction": direction, "stop": stop, "risk": risk}
    return signals


def fibonacci_filter_flags(bars, index, direction, lookback=3, scan=80):
    """Causal Fibonacci proximity test using only candles available at index."""
    start = max(0, index - scan - 2 * lookback)
    window = bars[start:index + 1]
    highs, lows = swing_points(window, lookback)
    if direction == "BUY":
        pairs = [(lo, hi) for lo in lows for hi in highs if lo[0] < hi[0]]
        if not pairs: return {"classic": False, "705": False}
        lo, hi = max(pairs, key=lambda pair: pair[1][0])
        swing_low, swing_high = lo[1], hi[1]
        levels = {r: swing_high - (swing_high - swing_low) * r for r in (0.382, 0.500, 0.618, 0.705, 0.786)}
    elif direction == "SELL":
        pairs = [(hi, lo) for hi in highs for lo in lows if hi[0] < lo[0]]
        if not pairs: return {"classic": False, "705": False}
        hi, lo = max(pairs, key=lambda pair: pair[1][0])
        swing_high, swing_low = hi[1], lo[1]
        levels = {r: swing_low + (swing_high - swing_low) * r for r in (0.382, 0.500, 0.618, 0.705, 0.786)}
    else:
        return {"classic": False, "705": False}
    if swing_high <= swing_low: return {"classic": False, "705": False}
    trs = []
    for j in range(max(1, len(window) - 14), len(window)):
        bar, previous = window[j], window[j - 1]["close"]
        trs.append(max(bar["high"] - bar["low"], abs(bar["high"] - previous), abs(bar["low"] - previous)))
    if not trs: return {"classic": False, "705": False}
    tolerance = 0.15 * (sum(trs) / len(trs))
    price = window[-1]["close"]
    classic = any(abs(price - levels[x]) <= tolerance for x in (0.382, 0.500, 0.618, 0.786))
    level_705 = abs(price - levels[0.705]) <= tolerance
    return {"classic": classic, "705": level_705}


def filter_signals_by_fibonacci(signals, bars, level_type):
    filtered = {}
    for index, signal in signals.items():
        flags = fibonacci_filter_flags(bars, index, signal["direction"])
        if flags[level_type]:
            filtered[index] = signal
    return filtered

def simulate(bars, signals, strategy):
    trades, active = [], None
    for i in range(1, len(bars)):
        bar = bars[i]
        had_open_trade_at_bar_start = active is not None
        if active:
            direction, stop, risk = active["direction"], active["stop"], active["risk"]
            target = active["entry"] + 2 * risk if direction == "BUY" else active["entry"] - 2 * risk
            hit_stop = bar["low"] <= stop if direction == "BUY" else bar["high"] >= stop
            hit_target = bar["high"] >= target if direction == "BUY" else bar["low"] <= target
            if hit_stop or hit_target or i - active["index"] >= 48:
                result_r = -1.0 if hit_stop else (2.0 if hit_target else ((bar["close"] - active["entry"]) / risk if direction == "BUY" else (active["entry"] - bar["close"]) / risk))
                trades.append({"strategy": strategy, "signal_time": active["signal_time"], "entry_time": bars[active["index"]]["time"],
                               "direction": direction, "entry": active["entry"], "stop": stop, "risk": risk,
                               "exit_time": bar["time"], "r_multiple": result_r})
                active = None
        # Do not open a new trade on a candle that was used to exit an older trade.
        if not had_open_trade_at_bar_start and active is None and i - 1 in signals:
            signal = signals[i - 1]
            entry = bar["open"]  # Enter only at the next candle open.
            risk = abs(entry - signal["stop"])
            if 0 < risk <= 4 * signal["risk"]:
                active = {"index": i, "signal_time": bars[i - 1]["time"], "entry": entry,
                          "direction": signal["direction"], "stop": signal["stop"], "risk": risk}
    if active:
        bar, risk = bars[-1], active["risk"]
        result_r = (bar["close"] - active["entry"]) / risk if active["direction"] == "BUY" else (active["entry"] - bar["close"]) / risk
        trades.append({"strategy": strategy, "signal_time": active["signal_time"], "entry_time": bars[active["index"]]["time"],
                       "direction": active["direction"], "entry": active["entry"], "stop": active["stop"],
                       "risk": risk, "exit_time": bar["time"], "r_multiple": result_r, "exit_reason": "end_of_data"})
    return trades


def metrics(trades):
    returns = [x["r_multiple"] for x in trades]
    wins, losses = [x for x in returns if x > 0], [x for x in returns if x < 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    equity = peak = max_dd = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {"trades": len(returns), "win_rate_pct": round(100 * len(wins) / len(returns), 2) if returns else 0,
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else (None if not gross_win else "inf"),
            "expectancy_R": round(sum(returns) / len(returns), 3) if returns else 0,
            "net_R": round(sum(returns), 3), "max_drawdown_R": round(max_dd, 3),
            "average_win_R": round(sum(wins) / len(wins), 3) if wins else 0,
            "average_loss_R": round(sum(losses) / len(losses), 3) if losses else 0}


def main():
    requested_days = int(os.getenv("BACKTEST_DAYS", "365"))
    bars, data_requests = fetch_m15(requested_days)
    signals = build_signals(bars)
    all_trades = []
    summary = {"instrument": "XAU/USD Spot (Twelve Data)", "timeframe": "M15", "bars": len(bars), "requested_days": requested_days, "data_requests": data_requests,
               "from_utc": bars[0]["time"], "to_utc": bars[-1]["time"],
               "execution_model": "Signal on closed candle; entry at next M15 open; stop-first if SL and TP touched in same candle; 2R target; maximum 48-bar hold.",
               "fibonacci_method": "Confirmed swing retracement; classic levels 0.382/0.500/0.618/0.786 and 0.705 tested separately; proximity tolerance 0.15 x recent 14-bar average true range; signal-candle close only.",
               "limitations": ["ICT is a rule-based OHLC approximation, not full discretionary ICT.",
                               "No spread, slippage, commission, swap, or HFM feed differences are modeled.",
                               "No order-book/Bookmap or fundamental/news filter.",
                               "The available provider history may be too short for statistical conclusions."],
               "strategies": {}}
    for name in ("Technical", "ICT"):
        variants = {
            name: signals[name],
            name + " + Fibonacci classic": filter_signals_by_fibonacci(signals[name], bars, "classic"),
            name + " + Fibonacci 0.705": filter_signals_by_fibonacci(signals[name], bars, "705"),
        }
        for variant_name, variant_signals in variants.items():
            trades = simulate(bars, variant_signals, variant_name)
            all_trades.extend(trades)
            summary["strategies"][variant_name] = metrics(trades)
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUTPUT / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        if all_trades:
            writer = csv.DictWriter(f, fieldnames=sorted({key for trade in all_trades for key in trade}))
            writer.writeheader()
            writer.writerows(all_trades)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
