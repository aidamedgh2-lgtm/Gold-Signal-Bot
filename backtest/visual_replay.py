"""Chronological visual replay using Twelve Data + two AI reviews.
This is a detector/reviewer replay, not a P/L backtest.
"""
import csv, datetime as dt, json, os, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from services.chart_detector import detect_visual_zones
from services.vision_review import assess_candidate
from strategy_fidelity import matching_lower_timeframes

API="https://api.twelvedata.com/time_series"
KEY=os.environ.get("TWELVEDATA_API_KEY","").strip()
AI=os.environ.get("GEMINI_API_KEY","").strip()
MODEL=os.environ.get("GEMINI_VISION_MODEL","gemini-3.5-flash-lite")
SYMBOL="XAU/USD"
TFS=[("15min","M15",dt.timedelta(minutes=15)),("1h","H1",dt.timedelta(hours=1)),("4h","H4",dt.timedelta(hours=4)),("1day","D1",dt.timedelta(days=1))]
OUT=Path("visual_replay_results")

def parse_utc(value):
    """Parse intraday timestamps and Twelve Data date-only D1 timestamps."""
    stamp=dt.datetime.fromisoformat(value)
    return stamp.replace(tzinfo=dt.timezone.utc) if stamp.tzinfo is None else stamp.astimezone(dt.timezone.utc)

def build_checkpoints(histories, n):
    """Start only after every timeframe has its minimum 20-candle context."""
    warmup = max(
        parse_utc(histories[label][0]["time"]) + delta * 19
        for _, label, delta in TFS
    )
    end = min(parse_utc(histories[label][-1]["time"]) for _, label, _ in TFS)
    if end <= warmup:
        raise RuntimeError(
            "Not enough overlapping history after the 20-candle warm-up "
            "across M15/H1/H4/D1"
        )
    return [warmup + (end - warmup) * i / (n - 1) for i in range(n)]


def fetch(interval, delta, days, now):
    params=urllib.parse.urlencode({"symbol":SYMBOL,"interval":interval,"outputsize":5000,"timezone":"UTC","order":"desc","end_date":now.strftime("%Y-%m-%d %H:%M:%S"),"apikey":KEY,"format":"JSON"})
    req=urllib.request.Request(API+"?"+params,headers={"User-Agent":"Gold-SD-Visual-Replay/1.0"})
    payload=None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req,timeout=45) as response:
                payload=json.loads(response.read().decode())
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise RuntimeError(
                    f"{interval}: Twelve Data request failed (HTTP {exc.code})"
                ) from exc
            retry_after=exc.headers.get("Retry-After")
            try:
                delay=float(retry_after) if retry_after else 20.0*(attempt+1)
            except (TypeError, ValueError):
                delay=20.0*(attempt+1)
            delay=min(max(delay,5.0),90.0)
            print(f"{interval}: Twelve Data rate limit; retrying in {delay:.0f}s")
            time.sleep(delay)
    if not isinstance(payload,dict) or "values" not in payload:
        message=payload.get("message") if isinstance(payload,dict) else "invalid provider response"
        raise RuntimeError(f"{interval}: {message}")
    start=now-dt.timedelta(days=days); bars=[]
    for x in payload["values"]:
        stamp=parse_utc(x["datetime"])
        if stamp<start or stamp+delta>now: continue
        bars.append({"time":x["datetime"],**{k:float(x[k]) for k in ("open","high","low","close")}})
    bars.sort(key=lambda x:x["time"])
    # The timestamp+interval filter above already excludes the still-forming
    # candle. Do not drop the newest remaining candle a second time.
    import math
    for bar in bars:
        values=[bar[k] for k in ("open","high","low","close")]
        if not all(math.isfinite(v) for v in values):
            raise RuntimeError(f"{interval}: non-finite OHLC value")
        if (bar["high"] < max(bar["open"],bar["close"],bar["low"])
                or bar["low"] > min(bar["open"],bar["close"],bar["high"])):
            raise RuntimeError(f"{interval}: invalid OHLC ordering")
    if len(bars)<20: raise RuntimeError(f"Insufficient closed {interval} candles: {len(bars)}")
    # Fail closed if the provider silently truncates the requested lookback.
    if bars[0]["time"] > start.strftime("%Y-%m-%d %H:%M:%S"):
        oldest=parse_utc(bars[0]["time"])
        if oldest-start > delta*2:
            raise RuntimeError(f"{interval}: incomplete {days}-day coverage; oldest candle is {oldest.isoformat()}")
    return bars

def main():
    if not KEY or not AI: raise SystemExit("Missing TWELVEDATA_API_KEY or GEMINI_API_KEY")
    days=int(os.getenv("REPLAY_DAYS") or "30"); n=int(os.getenv("REPLAY_SNAPSHOTS") or "6")
    if not 7<=days<=90 or not 2<=n<=12: raise SystemExit("Invalid replay window/snapshot count")
    now=dt.datetime.now(dt.timezone.utc); histories={}
    for interval,label,delta in TFS:
        histories[label]=fetch(interval,delta,days,now); print(f"{label}: {len(histories[label])} closed candles"); time.sleep(1)
    checkpoints=build_checkpoints(histories,n)
    records=[]
    for idx,point in enumerate(checkpoints,1):
        print(f"Checkpoint {idx}/{n}: {point.isoformat()}")
        for _,label,_delta in TFS:
            available=[b for b in histories[label] if parse_utc(b["time"])<=point]
            if len(available)<20:
                records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"INSUFFICIENT_HISTORY"}); continue
            window=available[-180:]
            try:
                zones=detect_visual_zones(window,label,AI,MODEL)
                time.sleep(4.5)
                if not zones: records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"NO_CLEAR_ZONE"})
                for z in zones:
                    candidate={**z,"tf":label,"created":z["origin_start"]}
                    review=assess_candidate(window,candidate,AI,MODEL)
                    agree=review["departure"]==z["departure"] and review["zone_readability"]=="clear"
                    records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"TWO_AI_AGREE" if agree else "REVIEW_DISAGREES","direction":z["direction"],"low":z["low"],"high":z["high"],"origin_start":z["origin_start"],"origin_end":z["origin_end"],"detector_departure":z["departure"],"review_departure":review["departure"],"approach":review["approach"],"readability":review["zone_readability"],"detector_confidence":z["confidence"],"review_confidence":review["confidence"],"evidence":z["evidence"],"review_evidence":review["evidence"]})
                    time.sleep(2)
            except Exception as exc:
                records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"ERROR","error":str(exc)[:500]}); print(f"{label}: {exc}")
    # Verify each candidate against matching lower-timeframe zones from the
    # same checkpoint. Direction and overlapping price area must both agree.
    by_checkpoint = {}
    for record in records:
        if "direction" in record and "low" in record and "high" in record:
            by_checkpoint.setdefault(record["checkpoint"], {}).setdefault(
                record["tf"], []
            ).append(record)
    for record in records:
        if "direction" not in record or "low" not in record or "high" not in record:
            continue
        aligned = matching_lower_timeframes(
            record["tf"], record,
            by_checkpoint.get(record["checkpoint"], {}),
        )
        record["mtf_aligned_timeframes"] = aligned["aligned_timeframes"]
        record["mtf_matched_lower_timeframes"] = aligned["matched_lower_timeframes"]
        record["mtf_points"] = aligned["points"]
        record["mtf_eligible"] = bool(
            aligned["eligible"] and record.get("status") == "TWO_AI_AGREE"
        )
        record["mtf_rejection_reason"] = (
            "" if record["mtf_eligible"] else
            (aligned["rejection_reason"] or "visual_review_not_agreed")
        )
    OUT.mkdir(exist_ok=True)
    (OUT/"replay.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    fields=sorted({k for r in records for k in r})
    with (OUT/"replay.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(records)
    counts={}
    for r in records: counts[r["status"]]=counts.get(r["status"],0)+1
    summary={"provider":"Twelve Data","vision_provider":"Google Gemini API","symbol":SYMBOL,"days":days,"checkpoints":n,"model":MODEL,"records":len(records),"status_counts":counts,"warning":"Visual detector/reviewer replay only; NOT a strategy P/L backtest. No profitability inferred."}
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
