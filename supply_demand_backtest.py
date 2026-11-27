"""Causal historical replay of the PR#5 Supply/Demand alert logic.

Uses closed Twelve Data XAU/USD OHLC bars. No broker execution, no Telegram,
and no order placement. This is a diagnostic replay, not proof of profitability.
"""
import bisect
import csv
import datetime as dt
import json
import math
import os
import urllib.parse
import urllib.request
import time
from pathlib import Path

import supply_demand_live as engine

API = "https://api.twelvedata.com/time_series"
KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()
OUTPUT = Path("sd_backtest_results")
OUTPUTSIZE = 5000
COST_R = float(os.getenv("SD_COST_R", "0.05"))
MAX_HOLD_BARS = int(os.getenv("SD_MAX_HOLD_BARS", "96"))
TIMEFRAMES = [
    ("1month", "MN1", "month"), ("1week", "W1", "week"),
    ("1day", "D1", "day"), ("4h", "H4", "4h"),
    ("1h", "H1", "1h"), ("15min", "M15", "15m"),
]


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def close_time(value, unit):
    start = parse_time(value)
    if unit == "month":
        year, month = start.year, start.month
        if month == 12:
            return start.replace(year=year + 1, month=1)
        return start.replace(year=year, month=month + 1)
    delta = {"week": dt.timedelta(days=7), "day": dt.timedelta(days=1),
             "4h": dt.timedelta(hours=4), "1h": dt.timedelta(hours=1),
             "15m": dt.timedelta(minutes=15)}[unit]
    return start + delta


def fetch(interval, label):
    if not KEY:
        raise RuntimeError("TWELVEDATA_API_KEY is missing in GitHub Actions secrets.")
    params = urllib.parse.urlencode({
        "symbol": "XAU/USD", "interval": interval, "outputsize": OUTPUTSIZE,
        "timezone": "UTC", "order": "desc", "apikey": KEY, "format": "JSON",
    })
    request = urllib.request.Request(API + "?" + params,
        headers={"User-Agent": "Gold-SD-Causal-Backtest/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "values" not in payload:
        raise RuntimeError(f"Twelve Data {label}: {payload.get('message') or payload}")
    raw_items = sorted(payload["values"], key=lambda item: item["datetime"])
    # Twelve Data can return decades of old history with malformed early OHLC.
    # Retain only the recent context needed for this M15 replay.
    history_limits = {"MN1": 36, "W1": 104, "D1": 260, "H4": 1000, "H1": 2500, "M15": 5000}
    raw_items = raw_items[-history_limits[label]:]
    rows, invalid = [], []
    for item in raw_items:
        try:
            bar = {"time": item["datetime"]}
            for key in ("open", "high", "low", "close"):
                bar[key] = float(item[key])
            valid = all(math.isfinite(bar[k]) for k in ("open", "high", "low", "close"))
            valid = valid and bar["high"] >= max(bar["open"], bar["close"], bar["low"])
            valid = valid and bar["low"] <= min(bar["open"], bar["close"], bar["high"])
            if not valid:
                invalid.append({k: bar.get(k) for k in ("time", "open", "high", "low", "close")})
                continue
            rows.append(bar)
        except (KeyError, TypeError, ValueError) as exc:
            invalid.append({"time": item.get("datetime"), "error": str(exc)})
    allowed_invalid = max(2, int(len(raw_items) * 0.005))
    if len(invalid) > allowed_invalid:
        raise RuntimeError(
            f"{label}: rejected {len(invalid)} invalid OHLC rows "
            f"(allowed {allowed_invalid}); samples={invalid[:3]}"
        )
    if invalid:
        print(f"WARNING {label}: excluded {len(invalid)} invalid provider rows; samples={invalid[:3]}")
    rows.sort(key=lambda x: x["time"])
    # Match live engine policy: discard newest potentially unfinished candle.
    if rows:
        rows = rows[:-1]
    if len(rows) < 35:
        raise RuntimeError(f"Insufficient closed {label} candles: {len(rows)}")
    print(f"{label}: {len(rows)} closed bars; {rows[0]['time']} -> {rows[-1]['time']}")
    return rows


def stats(trades):
    if not trades:
        return {"trades": 0, "win_rate_pct": None, "profit_factor": None,
                "expectancy_R": None, "net_R": 0.0, "max_drawdown_R": 0.0}
    values = [x["net_r"] for x in trades]
    wins = sum(x for x in values if x > 0)
    losses = -sum(x for x in values if x < 0)
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(values),
        "win_rate_pct": round(100 * sum(x > 0 for x in values) / len(values), 2),
        "profit_factor": round(wins / losses, 4) if losses else (None if wins == 0 else "inf"),
        "expectancy_R": round(sum(values) / len(values), 4),
        "net_R": round(sum(values), 4),
        "max_drawdown_R": round(max_dd, 4),
    }


def split_trades_by_time(trades, split_time):
    """Split trades at a fixed market-data timestamp, never by trade count."""
    in_sample = [trade for trade in trades if trade["signal_time"] < split_time]
    out_of_sample = [trade for trade in trades if trade["signal_time"] >= split_time]
    return in_sample, out_of_sample


def main():
    OUTPUT.mkdir(exist_ok=True)
    data = {}
    units = {}
    for index, (interval, label, unit) in enumerate(TIMEFRAMES):
        if index:
            print("Rate-limit pacing: waiting 12 seconds before next provider request.")
            time.sleep(12)
        data[label] = fetch(interval, label)
        units[label] = unit

    m15 = data["M15"]
    close_times = {
        tf: [close_time(bar["time"], units[tf]) for bar in bars]
        for tf, bars in data.items()
    }
    # Use only higher-timeframe bars fully closed by the current M15 close.
    cursors = {tf: 0 for tf in data}
    trades = []
    used_zones = set()
    next_free_index = 0
    warmup = 210

    for i in range(warmup, len(m15) - 1):
        now_closed = close_time(m15[i]["time"], "15m")
        prefixes = {}
        for _, tf, _ in TIMEFRAMES:
            cursor = bisect.bisect_right(close_times[tf], now_closed)
            cursors[tf] = cursor
            prefixes[tf] = data[tf][:cursor]
        if any(len(prefixes[tf]) < 35 for _, tf, _ in TIMEFRAMES):
            continue

        all_zones = []
        for _, tf, _ in TIMEFRAMES:
            all_zones.extend(engine.detect_zones(prefixes[tf], tf))
        if not all_zones:
            continue

        price = m15[i]["close"]
        candidates = []
        tf_order = [x[1] for x in TIMEFRAMES]
        for zone in all_zones:
            distance = max(zone["low"] - price, 0, price - zone["high"])
            if distance > engine.MAX_NEAR_ATR * zone["atr"]:
                continue
            if zone["direction"] == "DEMAND" and price < zone["low"] - 0.15 * zone["atr"]:
                continue
            if zone["direction"] == "SUPPLY" and price > zone["high"] + 0.15 * zone["atr"]:
                continue
            eligible = [
                other for other in all_zones if other is not zone
                and max(other["low"] - price, 0, price - other["high"]) <= engine.MAX_NEAR_ATR * other["atr"]
                and not ((other["direction"] == "DEMAND" and price < other["low"] - 0.15 * other["atr"])
                         or (other["direction"] == "SUPPLY" and price > other["high"] + 0.15 * other["atr"]))
            ]
            matches = engine.hierarchical_mtf_matches(zone, eligible)
            target = engine.opposing_zone_target(zone, all_zones)
            rr, rr_points = engine.rr_from_zone(zone, target, zone["stop"])
            score = (zone["move_points"] + rr_points + engine.mtf_points(matches)
                     + zone["visit_points"] + zone["duration_points"] + zone["arrival_points"])
            item = dict(zone)
            item.update(matches=matches, target=target, rr=rr,
                        rr_points=rr_points, mtf_points=engine.mtf_points(matches), score=score)
            candidates.append(item)

        if not candidates:
            continue
        candidates.sort(key=lambda z: (z["score"], -tf_order.index(z["tf"]), -z["move_atr"]), reverse=True)
        best = candidates[0]
        if best["score"] < 9 or i < next_free_index:
            continue
        if engine.confirmation(m15[:i + 1], best) is None:
            continue

        direction = "BUY" if best["direction"] == "DEMAND" else "SELL"
        zone_id = f'{best["tf"]}:{best["direction"]}:{best["low"]:.4f}:{best["high"]:.4f}:{best["created"]}'
        if zone_id in used_zones:
            continue

        entry_bar = m15[i + 1]
        entry = entry_bar["open"]
        stop = best["stop"]
        target = best["target"]
        risk = abs(entry - stop)
        if risk <= 0 or target is None:
            continue
        if (direction == "BUY" and not (stop < entry < target)) or (direction == "SELL" and not (target < entry < stop)):
            continue

        exit_price = None
        exit_reason = "TIME_EXIT"
        exit_index = min(len(m15) - 1, i + MAX_HOLD_BARS)
        for j in range(i + 1, exit_index + 1):
            bar = m15[j]
            if direction == "BUY":
                hit_stop, hit_target = bar["low"] <= stop, bar["high"] >= target
            else:
                hit_stop, hit_target = bar["high"] >= stop, bar["low"] <= target
            if hit_stop:
                exit_price, exit_reason, exit_index = stop, "STOP", j
                break
            if hit_target:
                exit_price, exit_reason, exit_index = target, "TARGET", j
                break
        if exit_price is None:
            exit_price = m15[exit_index]["close"]
        gross_r = ((exit_price - entry) if direction == "BUY" else (entry - exit_price)) / risk
        net_r = gross_r - COST_R
        trades.append({
            "signal_time": m15[i]["time"], "entry_time": entry_bar["time"],
            "exit_time": m15[exit_index]["time"], "direction": direction,
            "timeframe": best["tf"], "score": best["score"],
            "zone_low": best["low"], "zone_high": best["high"],
            "entry": entry, "stop": stop, "target": target,
            "exit": exit_price, "exit_reason": exit_reason,
            "gross_r": round(gross_r, 4), "cost_r": COST_R, "net_r": round(net_r, 4),
        })
        used_zones.add(zone_id)
        next_free_index = exit_index + 1

    split_time = m15[int(len(m15) * 0.70)]["time"]
    in_sample, out_of_sample = split_trades_by_time(trades, split_time)
    summary = {
        "source": "Twelve Data XAU/USD spot OHLC; not HFM broker feed",
        "m15_bars": len(m15), "requested_bars_per_timeframe": OUTPUTSIZE,
        "window_start_utc": m15[0]["time"], "window_end_utc": m15[-1]["time"],
        "chronological_split_time_utc": split_time,
        "entry_model": "next M15 candle open after closed confirmation",
        "exit_model": "opposing zone boundary; stop-first if stop and target hit in same candle",
        "max_holding_bars": MAX_HOLD_BARS, "cost_assumption_R_per_trade": COST_R,
        "visual_rules": "departure angle and approach shape remain OHLC proxies",
        "full_sample": stats(trades),
        "in_sample_first_70pct_by_time": stats(in_sample),
        "out_of_sample_last_30pct_by_time": stats(out_of_sample),
        "limitations": [
            "OHLC candles cannot reveal intrabar price path; stop-first is conservative.",
            "Spread, slippage, swaps and HFM-specific execution are not observed; cost is a configurable R proxy.",
            "The history is limited by provider outputsize and must not be treated as statistical proof.",
            "Only closed higher-timeframe bars are used at each replay timestamp.",
        ],
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with (OUTPUT / "trades.csv").open("w", newline="", encoding="utf-8") as file:
        fields = list(trades[0]) if trades else ["signal_time", "entry_time", "exit_time", "direction", "timeframe", "score", "entry", "stop", "target", "exit", "exit_reason", "gross_r", "cost_r", "net_r"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trades)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Artifacts written to {OUTPUT.resolve()}")


if __name__ == "__main__":
    main()
