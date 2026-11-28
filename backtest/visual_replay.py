"""Chronological PDF-strategy visual review.

This is a visual candidate-detection/review replay, NOT a P/L backtest.
Unknown criteria remain unknown; this program never emits trade orders.
"""
import csv
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from services.chart_detector import detect_visual_zones
from services.vision_review import assess_candidate
from strategy_fidelity import (\n    matching_lower_timeframes, count_zone_visits,\n    duration_points_by_timeframe, score_six_criteria,\n)

API = "https://api.twelvedata.com/time_series"
KEY = os.environ.get("TWELVEDATA_API_KEY", "").strip()
AI = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite")
SYMBOL = "XAU/USD"
# PDF hierarchy: largest to smallest. These are all required for the MTF audit.
TFS = [
    ("1month", "MN1", dt.timedelta(days=32)),
    ("1week", "W1", dt.timedelta(days=7)),
    ("1day", "D1", dt.timedelta(days=1)),
    ("4h", "H4", dt.timedelta(hours=4)),
    ("1h", "H1", dt.timedelta(hours=1)),
    ("15min", "M15", dt.timedelta(minutes=15)),
]
# Extra pre-window context is needed to avoid beginning a 90-day replay
# without the higher-timeframe history required by the PDF.
CONTEXT_DAYS = {
    "MN1": 760, "W1": 220, "D1": 35, "H4": 12, "H1": 3, "M15": 3,
}
OUT = Path("visual_replay_results")
PAGE_SIZE = 5000
MAX_PAGES = 30


def parse_utc(value):
    stamp = dt.datetime.fromisoformat(value)
    return stamp.replace(tzinfo=dt.timezone.utc) if stamp.tzinfo is None else stamp.astimezone(dt.timezone.utc)


def candle_close_time(bar, interval):
    """Return the actual close boundary; never expose an unfinished HTF candle."""
    stamp = parse_utc(bar["time"])
    if interval == "1month":
        year, month = stamp.year, stamp.month
        if month == 12:
            return dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
        return dt.datetime(year, month + 1, 1, tzinfo=dt.timezone.utc)
    if interval == "1week":
        return stamp + dt.timedelta(days=7)
    delta = dict(TFS)[interval]
    return stamp + delta


def build_checkpoints(histories, n, replay_start=None, replay_end=None):
    """Build chronological checkpoints, requiring 20 closed context bars per TF."""
    if replay_start is None:
        warmup = max(
            parse_utc(histories[label][0]["time"]) + delta * 19
            for _interval, label, delta in TFS
        )
        start = warmup
    else:
        start = replay_start
        for interval, label, _delta in TFS:
            ready = sum(
                1 for bar in histories[label]
                if candle_close_time(bar, interval) <= start
            )
            if ready < 20:
                raise RuntimeError(
                    f"{label}: only {ready} fully closed warm-up candles before replay start; need 20"
                )

    # Use the latest common closed time among daily and intraday data.
    end_labels = {"D1", "H4", "H1", "M15"}
    latest = []
    for interval, label, _delta in TFS:
        if label in end_labels:
            latest.append(max(candle_close_time(bar, interval) for bar in histories[label]))
    end = min(latest)
    if replay_end is not None:
        end = min(end, replay_end)
    if end <= start:
        raise RuntimeError("Insufficient overlapping closed-candle history for requested replay window")
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def fetch(interval, delta, days, now, context_days=0, outputsize=PAGE_SIZE):
    """Fetch every required closed candle using descending cursor pagination."""
    start = now - dt.timedelta(days=days + context_days)
    cursor_end = now
    collected = {}
    request_count = 0

    while cursor_end > start and request_count < MAX_PAGES:
        params = urllib.parse.urlencode({
            "symbol": SYMBOL,
            "interval": interval,
            "outputsize": outputsize,
            "timezone": "UTC",
            "order": "desc",
            "end_date": cursor_end.strftime("%Y-%m-%d %H:%M:%S"),
            "apikey": KEY,
            "format": "JSON",
        })
        request = urllib.request.Request(
            API + "?" + params,
            headers={"User-Agent": "Gold-SD-Visual-Replay/2.0"},
        )
        payload = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == 4:
                    raise RuntimeError(
                        f"{interval}: Twelve Data request failed (HTTP {exc.code})"
                    ) from exc
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 20.0 * (attempt + 1)
                except (TypeError, ValueError):
                    delay = 20.0 * (attempt + 1)
                delay = min(max(delay, 5.0), 90.0)
                print(f"{interval}: Twelve Data rate limit; retrying in {delay:.0f}s")
                time.sleep(delay)

        request_count += 1
        if not isinstance(payload, dict) or "values" not in payload:
            message = payload.get("message") if isinstance(payload, dict) else "invalid provider response"
            raise RuntimeError(f"{interval}: {message}")
        values = payload["values"]
        if not values:
            break

        stamps = []
        for item in values:
            stamp = parse_utc(item["datetime"])
            stamps.append(stamp)
            bar = {
                "time": item["datetime"],
                **{key: float(item[key]) for key in ("open", "high", "low", "close")},
            }
            if stamp >= start and candle_close_time(bar, interval) <= now:
                collected[bar["time"]] = bar

        oldest = min(stamps)
        if oldest <= start:
            break
        if len(values) < outputsize:
            # A few missing bars at the exact lookback boundary can be caused
            # by a market closure; larger gaps mean provider truncation.
            if oldest - start > max(delta * 3, dt.timedelta(days=3)):
                raise RuntimeError(
                    f"{interval}: incomplete history; oldest candle {oldest.isoformat()} "
                    f"is too recent for required context beginning {start.isoformat()}"
                )
            break
        next_end = oldest - dt.timedelta(seconds=1)
        if next_end >= cursor_end:
            raise RuntimeError(f"{interval}: pagination made no progress")
        cursor_end = next_end
        if cursor_end > start:
            time.sleep(8.5)

    if request_count >= MAX_PAGES:
        oldest_loaded = min((parse_utc(x) for x in collected), default=now)
        if oldest_loaded > start + dt.timedelta(days=3):
            raise RuntimeError(f"{interval}: exceeded {MAX_PAGES} pages; history is incomplete")

    bars = [collected[key] for key in sorted(collected)]
    import math
    for bar in bars:
        values = [bar[key] for key in ("open", "high", "low", "close")]
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError(f"{interval}: non-finite OHLC value")
        if (bar["high"] < max(bar["open"], bar["close"], bar["low"])
                or bar["low"] > min(bar["open"], bar["close"], bar["high"])):
            raise RuntimeError(f"{interval}: invalid OHLC ordering")
    if len(bars) < 20:
        raise RuntimeError(f"Insufficient fully closed {interval} candles: {len(bars)}")
    print(f"{interval}: {len(bars)} closed candles across {request_count} request(s)")
    return bars


def main():
    if not KEY or not AI:
        raise SystemExit("Missing TWELVEDATA_API_KEY or GEMINI_API_KEY")
    days = int(os.getenv("REPLAY_DAYS") or "90")
    count = int(os.getenv("REPLAY_SNAPSHOTS") or "6")
    if not 7 <= days <= 90 or not 2 <= count <= 12:
        raise SystemExit("Invalid replay window/snapshot count")

    now = dt.datetime.now(dt.timezone.utc)
    replay_start = now - dt.timedelta(days=days)
    histories = {}
    for interval, label, delta in TFS:
        histories[label] = fetch(
            interval, delta, days, now,
            context_days=CONTEXT_DAYS[label],
        )
        time.sleep(8.5)

    checkpoints = build_checkpoints(histories, count, replay_start=replay_start, replay_end=now)
    records = []
    for checkpoint_index, point in enumerate(checkpoints, 1):
        print(f"Checkpoint {checkpoint_index}/{count}: {point.isoformat()}")
        for interval, label, _delta in TFS:
            available = [
                bar for bar in histories[label]
                if candle_close_time(bar, interval) <= point
            ]
            if len(available) < 20:
                records.append({
                    "checkpoint": checkpoint_index, "time_utc": point.isoformat(),
                    "tf": label, "status": "INSUFFICIENT_HISTORY",
                })
                continue
            window = available[-180:]
            try:
                zones = detect_visual_zones(window, label, AI, MODEL)
                time.sleep(4.5)
                if not zones:
                    records.append({
                        "checkpoint": checkpoint_index, "time_utc": point.isoformat(),
                        "tf": label, "status": "NO_CLEAR_ZONE",
                    })
                for zone in zones:
                    candidate = {**zone, "tf": label, "created": zone["origin_start"]}
                    review = assess_candidate(window, candidate, AI, MODEL)
                    agreed = (
                        review["departure"] == zone["departure"]
                        and review["zone_readability"] == "clear"
                    )
                    origin_index = next(
                        (i for i, bar in enumerate(available)
                         if bar["time"] == zone["origin_start"]),
                        None,
                    )
                    if origin_index is None:
                        raise RuntimeError("Origin candle is absent from closed history")
                    visits = count_zone_visits(
                        available, zone["low"], zone["high"], origin_index
                    )
                    origin_close = candle_close_time(
                        available[origin_index], interval
                    )
                    d1_after = [
                        bar for bar in histories["D1"]
                        if origin_close < candle_close_time(bar, "1day") <= point
                    ]
                    h4_after = [
                        bar for bar in histories["H4"]
                        if origin_close < candle_close_time(bar, "4h") <= point
                    ]
                    duration = duration_points_by_timeframe(
                        d1_after, h4_after, zone["low"], zone["high"]
                    )
                    # R:R stays unresolved: the PDF requires the prior opposing
                    # destination and a planned entry/stop, neither may be guessed.
                    partial_score = score_six_criteria(
                        departure_visual=(
                            review["departure"] if agreed else None
                        ),
                        approach_visual=review["approach"],
                        rr_points=None,
                        mtf_points=0,
                        visits=visits,
                        duration_points_value=duration["score"],
                    )
                    records.append({
                        "checkpoint": checkpoint_index,
                        "time_utc": point.isoformat(),
                        "tf": label,
                        "status": "TWO_AI_AGREE" if agreed else "REVIEW_DISAGREES",
                        "direction": zone["direction"],
                        "low": zone["low"],
                        "high": zone["high"],
                        "origin_start": zone["origin_start"],
                        "origin_end": zone["origin_end"],
                        "detector_departure": zone["departure"],
                        "review_departure": review["departure"],
                        "approach": review["approach"],
                        "readability": review["zone_readability"],
                        "detector_confidence": zone["confidence"],
                        "review_confidence": review["confidence"],
                        "evidence": zone["evidence"],
                        "review_evidence": review["evidence"],
                        "unknown_reason": review["unknown_reason"],
                        "zone_visits": visits,
                        "visit_points": partial_score["criteria"]["visits"],
                        "d1_duration_touch_count": duration["d1_count"],
                        "h4_duration_touch_count": duration["h4_count"],
                        "duration_points": duration["score"],
                        "rr_points": None,
                        "partial_criteria": partial_score["criteria"],
                        "final_score_complete": partial_score["complete"],
                        "final_score_total": partial_score["total"],
                    })
                    time.sleep(2)
            except Exception as exc:
                records.append({
                    "checkpoint": checkpoint_index, "time_utc": point.isoformat(),
                    "tf": label, "status": "ERROR", "error": str(exc)[:500],
                })
                print(f"{label}: {exc}")

    by_checkpoint = {}
    for record in records:
        if all(key in record for key in ("direction", "low", "high")):
            by_checkpoint.setdefault(record["checkpoint"], {}).setdefault(
                record["tf"], []
            ).append(record)

    for record in records:
        if not all(key in record for key in ("direction", "low", "high")):
            continue
        aligned = matching_lower_timeframes(
            record["tf"], record, by_checkpoint.get(record["checkpoint"], {})
        )
        record["mtf_aligned_timeframes"] = aligned["aligned_timeframes"]
        record["mtf_matched_lower_timeframes"] = aligned["matched_lower_timeframes"]
        record["mtf_points"] = aligned["points"]
        record["partial_criteria"]["mtf"] = aligned["points"]
        record["mtf_eligible"] = bool(
            aligned["eligible"] and record.get("status") == "TWO_AI_AGREE"
        )
        record["mtf_rejection_reason"] = (
            "" if record["mtf_eligible"]
            else (aligned["rejection_reason"] or "visual_review_not_agreed")
        )

    OUT.mkdir(exist_ok=True)
    (OUT / "replay.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = sorted({key for record in records for key in record})
    with (OUT / "replay.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)

    counts = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    error_count = counts.get("ERROR", 0)
    summary = {
        "provider": "Twelve Data",
        "vision_provider": "Google Gemini API",
        "symbol": SYMBOL,
        "requested_replay_days": days,
        "checkpoints": count,
        "model": MODEL,
        "timeframes": [label for _interval, label, _delta in TFS],
        "replay_start_utc": replay_start.isoformat(),
        "last_common_closed_checkpoint_utc": checkpoints[-1].isoformat(),
        "records": len(records),
        "status_counts": counts,
        "errors": error_count,
        "scope": "Visual zone detection, independent visual review and hierarchical MTF matching only.",
        "not_computed": [
            "Final six-criterion /10 score",
            "Source-defined opposing target and reward/risk",
            "Trade entry/stop levels",
            "Profit/loss, win rate or profitability",
        ],
        "warning": (
            "This is a visual detector/reviewer replay, NOT a complete six-criterion "
            "strategy backtest and NOT a P/L backtest. No profitability is inferred."
        ),
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if error_count:
        raise SystemExit(
            f"Replay contains {error_count} API/processing error(s); refusing a green workflow."
        )


if __name__ == "__main__":
    main()
