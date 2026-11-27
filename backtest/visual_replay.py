"""Chronological visual replay using Twelve Data + two AI reviews.
This is a detector/reviewer replay, not a P/L backtest.
"""
import csv, datetime as dt, json, os, time, urllib.parse, urllib.request
from pathlib import Path
from services.chart_detector import detect_visual_zones
from services.vision_review import assess_candidate

API="https://api.twelvedata.com/time_series"
KEY=os.environ.get("TWELVEDATA_API_KEY","").strip()
AI=os.environ.get("OPENAI_API_KEY","").strip()
MODEL=os.environ.get("OPENAI_VISION_MODEL","gpt-4.1-mini")
SYMBOL="XAU/USD"
TFS=[("15min","M15",dt.timedelta(minutes=15)),("1h","H1",dt.timedelta(hours=1)),("4h","H4",dt.timedelta(hours=4)),("1day","D1",dt.timedelta(days=1))]
OUT=Path("visual_replay_results")

def fetch(interval, delta, days, now):
    params=urllib.parse.urlencode({"symbol":SYMBOL,"interval":interval,"outputsize":5000,"timezone":"UTC","order":"desc","end_date":now.strftime("%Y-%m-%d %H:%M:%S"),"apikey":KEY,"format":"JSON"})
    req=urllib.request.Request(API+"?"+params,headers={"User-Agent":"Gold-SD-Visual-Replay/1.0"})
    with urllib.request.urlopen(req,timeout=45) as r: payload=json.loads(r.read().decode())
    if "values" not in payload: raise RuntimeError(f"{interval}: {payload.get('message') or payload}")
    start=now-dt.timedelta(days=days); bars=[]
    for x in payload["values"]:
        stamp=dt.datetime.strptime(x["datetime"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
        if stamp<start or stamp+delta>now: continue
        bars.append({"time":x["datetime"],**{k:float(x[k]) for k in ("open","high","low","close")}})
    bars.sort(key=lambda x:x["time"])
    if len(bars)>1: bars=bars[:-1]
    if len(bars)<20: raise RuntimeError(f"Insufficient closed {interval} candles: {len(bars)}")
    return bars

def main():
    if not KEY or not AI: raise SystemExit("Missing TWELVEDATA_API_KEY or OPENAI_API_KEY")
    days=int(os.getenv("REPLAY_DAYS","30")); n=int(os.getenv("REPLAY_SNAPSHOTS","6"))
    if not 7<=days<=90 or not 2<=n<=12: raise SystemExit("Invalid replay window/snapshot count")
    now=dt.datetime.now(dt.timezone.utc); histories={}
    for interval,label,delta in TFS:
        histories[label]=fetch(interval,delta,days,now); print(f"{label}: {len(histories[label])} closed candles"); time.sleep(1)
    end=min(dt.datetime.strptime(v[-1]["time"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc) for v in histories.values())
    start=end-dt.timedelta(days=days)
    checkpoints=[start+(end-start)*i/(n-1) for i in range(n)]
    records=[]
    for idx,point in enumerate(checkpoints,1):
        print(f"Checkpoint {idx}/{n}: {point.isoformat()}")
        for _,label,_delta in TFS:
            available=[b for b in histories[label] if dt.datetime.strptime(b["time"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)<=point]
            if len(available)<20:
                records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"INSUFFICIENT_HISTORY"}); continue
            window=available[-180:]
            try:
                zones=detect_visual_zones(window,label,AI,MODEL)
                if not zones: records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"NO_CLEAR_ZONE"})
                for z in zones:
                    candidate={**z,"tf":label,"created":z["origin_start"]}
                    review=assess_candidate(window,candidate,AI,MODEL)
                    agree=review["departure"]==z["departure"] and review["zone_readability"]=="clear"
                    records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"TWO_AI_AGREE" if agree else "REVIEW_DISAGREES","direction":z["direction"],"low":z["low"],"high":z["high"],"origin_start":z["origin_start"],"origin_end":z["origin_end"],"detector_departure":z["departure"],"review_departure":review["departure"],"approach":review["approach"],"readability":review["zone_readability"],"detector_confidence":z["confidence"],"review_confidence":review["confidence"],"evidence":z["evidence"],"review_evidence":review["evidence"]})
                    time.sleep(1)
            except Exception as exc:
                records.append({"checkpoint":idx,"time_utc":point.isoformat(),"tf":label,"status":"ERROR","error":str(exc)[:500]}); print(f"{label}: {exc}")
    OUT.mkdir(exist_ok=True)
    (OUT/"replay.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    fields=sorted({k for r in records for k in r})
    with (OUT/"replay.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(records)
    counts={}
    for r in records: counts[r["status"]]=counts.get(r["status"],0)+1
    summary={"provider":"Twelve Data","symbol":SYMBOL,"days":days,"checkpoints":n,"model":MODEL,"records":len(records),"status_counts":counts,"warning":"Visual detector/reviewer replay only; NOT a strategy P/L backtest. No profitability inferred."}
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
