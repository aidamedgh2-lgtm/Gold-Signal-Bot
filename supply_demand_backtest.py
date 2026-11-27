"""Historical backtest for the live Supply & Demand XAU/USD strategy.

Uses only closed candles, replays the live zone/scoring/confirmation rules,
and never imports or calls Telegram send(). TP1 (1.5R) is the sole exit target
because the live alert does not define partial-position allocation.
"""
import bisect
import csv
import datetime as dt
import json
import math
import os
import urllib.parse
import urllib.request
from pathlib import Path

import supply_demand_live as live

OUTPUT_DIR = Path("supply_demand_backtest_results")
OUTPUTSIZE = int(os.environ.get("SD_BACKTEST_OUTPUTSIZE", "5000"))
COST_R = float(os.environ.get("SD_BACKTEST_COST_R", "0.05"))
TIMEFRAMES = [
    ("1month", "MN1", "month"),
    ("1week", "W1", "week"),
    ("1day", "D1", "day"),
    ("4h", "H4", "4h"),
    ("1h", "H1", "hour"),
    ("15min", "M15", "15min"),
]
TF_ORDER = [x[1] for x in TIMEFRAMES]


def parse_time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def valid_ohlc(bar):
    """Return whether OHLC values form a finite, positive, internally consistent candle."""
    values = [bar[field] for field in ("open", "high", "low", "close")]
    return (
        all(math.isfinite(value) and value > 0 for value in values)
        and bar["high"] >= max(bar["open"], bar["close"], bar["low"])
        and bar["low"] <= min(bar["open"], bar["close"], bar["high"])
    )


def candle_end(start, kind):
    if kind == "month":
        year = start.year + (1 if start.month == 12 else 0)
        month = 1 if start.month == 12 else start.month + 1
        return start.replace(year=year, month=month, day=1)
    delta = {"week": dt.timedelta(days=7), "day": dt.timedelta(days=1),
             "4h": dt.timedelta(hours=4), "hour": dt.timedelta(hours=1),
             "15min": dt.timedelta(minutes=15)}[kind]
    return start + delta


def deduplicate_bars(bars, label):
    """Remove only byte-for-byte equivalent OHLC duplicates; reject conflicting rows."""
    unique = {}
    duplicates = 0
    for bar in bars:
        stamp = bar["time"]
        values = tuple(bar[field] for field in ("open", "high", "low", "close"))
        if stamp in unique:
            previous = tuple(unique[stamp][field]
                             for field in ("open", "high", "low", "close"))
            if values != previous:
                raise RuntimeError(
                    f"{label}: conflicting duplicate timestamp {stamp}; "
                    "refusing to choose between different OHLC candles."
                )
            duplicates += 1
            continue
        unique[stamp] = bar
    return sorted(unique.values(), key=lambda x: x["_start"]), duplicates


def fetch_history(interval, label, kind):
    key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TWELVEDATA_API_KEY is missing.")
    params = urllib.parse.urlencode({
        "symbol": live.SYMBOL, "interval": interval, "outputsize": OUTPUTSIZE,
        "timezone": "UTC", "apikey": key, "format": "JSON",
    })
    req = urllib.request.Request(
        live.API + "?" + params, headers={"User-Agent": "Gold-SD-Historical-Research/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "values" not in payload:
        raise RuntimeError(f"{label}: {payload.get('message') or payload}")
    bars = []
    invalid_rows = []
    raw_values = payload["values"]
    for item in raw_values:
        stamp = str(item.get("datetime", "<missing timestamp>"))
        try:
            bar = {"time": stamp}
            for field in ("open", "high", "low", "close"):
                bar[field] = float(item[field])
            values = [bar[field] for field in ("open", "high", "low", "close")]
            if not valid_ohlc(bar):
                invalid_rows.append(f"{stamp} OHLC={values}")
                continue
            start = parse_time(stamp)
            bar["_start"] = start
            bar["_end"] = candle_end(start, kind)
            bars.append(bar)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            invalid_rows.append(f"{stamp} ({type(exc).__name__}: {exc})")

    # Some long-range provider responses contain isolated malformed legacy rows.
    # Skip a very small number, but fail closed if data quality is broadly poor.
    max_invalid = max(2, math.ceil(len(raw_values) * 0.001))
    if len(invalid_rows) > max_invalid:
        sample = "; ".join(invalid_rows[:5])
        raise RuntimeError(
            f"{label}: rejected {len(invalid_rows)}/{len(raw_values)} invalid OHLC rows "
            f"(limit {max_invalid}); examples: {sample}"
        )
    if invalid_rows:
        print(f"{label}: skipped {len(invalid_rows)} invalid provider OHLC row(s): "
              + "; ".join(invalid_rows[:3]))
    bars, duplicate_count = deduplicate_bars(bars, label)
    if duplicate_count:
        print(f"{label}: ignored {duplicate_count} exact duplicate OHLC rows")
    now = dt.datetime.now(dt.timezone.utc)
    # Keep only fully closed candles; timestamps are treated as candle-open times.
    bars = [b for b in bars if b["_end"] <= now]
    if len(bars) < 35:
        raise RuntimeError(f"{label}: only {len(bars)} fully closed candles; need >=35.")
    return bars


def strip_internal(bars):
    return [{k: b[k] for k in ("time", "open", "high", "low", "close")} for b in bars]


def score_candidates(all_zones, price):
    """Mirror the candidate validity, MTF matching, score and ranking in live.main()."""
    candidates = []
    for zone in all_zones:
        distance = max(zone["low"] - price, 0, price - zone["high"])
        if distance > live.MAX_NEAR_ATR * zone["atr"]:
            continue
        if zone["direction"] == "DEMAND" and price < zone["low"] - 0.15 * zone["atr"]:
            continue
        if zone["direction"] == "SUPPLY" and price > zone["high"] + 0.15 * zone["atr"]:
            continue
        matches = [
            other for other in all_zones
            if other is not zone and other["direction"] == zone["direction"]
            and other["tf"] != zone["tf"] and live.overlaps(zone, other)
            and max(other["low"] - price, 0, price - other["high"])
                <= live.MAX_NEAR_ATR * zone["atr"]
            and not (
                (other["direction"] == "DEMAND" and price < other["low"] - 0.15 * other["atr"])
                or (other["direction"] == "SUPPLY" and price > other["high"] + 0.15 * other["atr"])
            )
        ]
        zone = dict(zone)
        zone["matches"] = sorted({x["tf"] for x in matches}, key=TF_ORDER.index)
        match_count = 1 + len(zone["matches"])
        zone["mtf_points"] = 2 if match_count >= 3 else (1 if match_count == 2 else 0)
        zone["score"] = (zone["move_points"] + zone["rr_points"] + zone["mtf_points"]
                         + zone["visit_points"] + zone["duration_points"]
                         + zone["arrival_points"])
        candidates.append(zone)
    candidates.sort(
        key=lambda z: (z["score"], -TF_ORDER.index(z["tf"]), -z["move_atr"]),
        reverse=True,
    )
    return candidates


def simulate_trade(bars, entry_index, direction, entry, stop, cost_r=COST_R):
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if (direction == "BUY" and stop >= entry) or (direction == "SELL" and stop <= entry):
        return None
    target = entry + (1.5 * risk if direction == "BUY" else -1.5 * risk)
    for j in range(entry_index + 1, len(bars)):
        bar = bars[j]
        if direction == "BUY":
            if bar["open"] <= stop:
                exit_price, reason = bar["open"], "stop_gap"
            elif bar["open"] >= target:
                exit_price, reason = target, "tp1_gap"
            elif bar["low"] <= stop and bar["high"] >= target:
                exit_price, reason = stop, "stop_and_tp_same_bar_stop_first"
            elif bar["low"] <= stop:
                exit_price, reason = stop, "stop"
            elif bar["high"] >= target:
                exit_price, reason = target, "tp1"
            else:
                continue
        else:
            if bar["open"] >= stop:
                exit_price, reason = bar["open"], "stop_gap"
            elif bar["open"] <= target:
                exit_price, reason = target, "tp1_gap"
            elif bar["high"] >= stop and bar["low"] <= target:
                exit_price, reason = stop, "stop_and_tp_same_bar_stop_first"
            elif bar["high"] >= stop:
                exit_price, reason = stop, "stop"
            elif bar["low"] <= target:
                exit_price, reason = target, "tp1"
            else:
                continue
        gross_r = ((exit_price - entry) / risk if direction == "BUY"
                   else (entry - exit_price) / risk)
        return {"exit_index": j, "exit_time": bar["time"], "exit_price": exit_price,
                "exit_reason": reason, "gross_r": gross_r, "net_r": gross_r - cost_r}
    # Close any open position at the last available close to avoid silently dropping it.
    last = bars[-1]
    gross_r = ((last["close"] - entry) / risk if direction == "BUY"
               else (entry - last["close"]) / risk)
    return {"exit_index": len(bars)-1, "exit_time": last["time"],
            "exit_price": last["close"], "exit_reason": "end_of_data",
            "gross_r": gross_r, "net_r": gross_r - cost_r}


def max_drawdown_r(trades):
    equity = peak = 0.0
    worst = 0.0
    for trade in trades:
        equity += trade["net_r"]
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return round(worst, 4)


def summarize(trades):
    if not trades:
        return {"trades": 0, "win_rate_pct": None, "profit_factor": None,
                "expectancy_net_r": None, "net_r": 0.0, "max_drawdown_r": 0.0}
    wins = [t["net_r"] for t in trades if t["net_r"] > 0]
    losses = [t["net_r"] for t in trades if t["net_r"] < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        "trades": len(trades),
        "win_rate_pct": round(100 * sum(t["net_r"] > 0 for t in trades) / len(trades), 2),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "expectancy_net_r": round(sum(t["net_r"] for t in trades) / len(trades), 4),
        "net_r": round(sum(t["net_r"] for t in trades), 4),
        "max_drawdown_r": max_drawdown_r(trades),
        "average_win_r": round(sum(wins) / len(wins), 4) if wins else None,
        "average_loss_r": round(sum(losses) / len(losses), 4) if losses else None,
    }


def run():
    histories = {}
    for interval, label, kind in TIMEFRAMES:
        histories[label] = fetch_history(interval, label, kind)
        print(f"{label}: {len(histories[label])} fully closed bars "
              f"({histories[label][0]['time']} .. {histories[label][-1]['time']})")
    m15 = histories["M15"]
    tf_end_times = {
        label: [b["_end"] for b in histories[label]]
        for _, label, _ in TIMEFRAMES if label != "M15"
    }
    tf_starts = {label: [b["_start"] for b in histories[label]]
                 for label in tf_end_times}
    m15_plain = strip_internal(m15)
    trades, seen_zones = [], set()
    last_exit_index = -1
    signal_count = 0
    for i in range(34, len(m15)):
        decision_time = m15[i]["_end"]
        price = m15[i]["close"]
        all_zones = []
        for label in TF_ORDER:
            if label == "M15":
                prefix = m15_plain[:i+1]
            else:
                n = bisect.bisect_right(tf_end_times[label], decision_time)
                prefix = strip_internal(histories[label][:n])
            if len(prefix) >= 35:
                all_zones.extend(live.detect_zones(prefix, label))
        if not all_zones:
            continue
        candidates = score_candidates(all_zones, price)
        if not candidates:
            continue
        best = candidates[0]
        if best["score"] <= 8:
            continue
        confirmation = live.confirmation(m15_plain[:i+1], best)
        if not confirmation:
            continue
        zone_id = (f'{best["tf"]}:{best["direction"]}:{best["low"]:.2f}:'
                   f'{best["high"]:.2f}:{best["created"]}')
        if zone_id in seen_zones:
            continue
        seen_zones.add(zone_id)
        signal_count += 1
        if i <= last_exit_index:
            continue  # one position at a time; no overlapping exposure
        direction = "BUY" if best["direction"] == "DEMAND" else "SELL"
        entry = m15[i]["close"]
        stop = best["stop"]
        result = simulate_trade(m15_plain, i, direction, entry, stop)
        if result is None:
            continue
        trade = {
            "signal_time": m15[i]["time"], "direction": direction,
            "zone_tf": best["tf"], "zone_low": round(best["low"], 5),
            "zone_high": round(best["high"], 5), "score": best["score"],
            "confirmation": confirmation, "entry": entry, "stop": stop,
            "target_tp1": entry + (1.5 * abs(entry-stop) if direction == "BUY"
                                   else -1.5 * abs(entry-stop)),
            **result,
        }
        trades.append(trade)
        last_exit_index = result["exit_index"]

    OUTPUT_DIR.mkdir(exist_ok=True)
    with (OUTPUT_DIR / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        if trades:
            writer = csv.DictWriter(f, fieldnames=list(trades[0]))
            writer.writeheader()
            writer.writerows(trades)
    split = int(len(trades) * 0.7)
    report = {
        "strategy": "Live Supply & Demand (replay of current code)",
        "data_source": "Twelve Data XAU/USD OHLC; not broker HFM execution data",
        "timestamp_assumption": "API datetime is candle-open UTC; only candles whose calculated close <= decision time are used",
        "exit_policy": "single full-position TP1 at 1.5R or SL; TP2/TP3 not modeled because no partial-exit sizing is defined",
        "position_policy": "one position at a time; no overlapping trades",
        "cost_model": f"fixed {COST_R:.4f}R deducted per closed trade; proxy, not measured spread/slippage",
        "signal_count_before_position_filter": signal_count,
        "timeframes": {label: {"bars": len(histories[label]),
                               "first": histories[label][0]["time"],
                               "last": histories[label][-1]["time"]}
                       for label in TF_ORDER},
        "all_trades": summarize(trades),
        "chronological_first_70pct": summarize(trades[:split]),
        "chronological_last_30pct_out_of_sample": summarize(trades[split:]),
        "trades": trades,
        "limitations": [
            "Twelve Data spot OHLC is not HFM bid/ask execution history.",
            "No tick data; intrabar stop/target collisions are resolved stop-first.",
            "Fixed transaction-cost deduction is a sensitivity proxy, not a measured spread.",
            "TP1-only full exit is an explicit test convention; live alerts also publish TP2/TP3.",
            "A short history or small trade count cannot establish durable profitability.",
        ],
    }
    (OUTPUT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "all_trades", "chronological_first_70pct",
        "chronological_last_30pct_out_of_sample", "signal_count_before_position_filter")},
        ensure_ascii=False, indent=2))
    print(f"Artifacts saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    run()
