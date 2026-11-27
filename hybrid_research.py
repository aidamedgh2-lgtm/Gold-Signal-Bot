"""Isolated M1/M5 hybrid research replay. No Telegram and no broker execution."""
import bisect
import csv
import json
import math
import os
import statistics
from pathlib import Path

import supply_demand_live as live
import supply_demand_backtest as bt

OUT = Path("hybrid_research_results")
HISTORY = [
    ("1month", "MN1", "month"), ("1week", "W1", "week"),
    ("1day", "D1", "day"), ("4h", "H4", "4h"),
    ("1h", "H1", "hour"), ("15min", "M15", "15min"),
    ("5min", "M5", "5min"), ("1min", "M1", "1min"),
]
ZONE_TFS = ["MN1", "W1", "D1", "H4", "H1", "M15"]


def mss_confirmation(m1, zone):
    """Closed M1 market-structure shift after a recent zone touch."""
    if len(m1) < 8:
        return None
    recent = m1[-5:]
    if not any(x["low"] <= zone["high"] and x["high"] >= zone["low"] for x in recent[:-1]):
        return None
    prev, cur = m1[-6:-1], m1[-1]
    if zone["direction"] == "DEMAND":
        swing = max(x["high"] for x in prev)
        return "M1 bullish MSS" if cur["close"] > swing and cur["close"] > cur["open"] else None
    swing = min(x["low"] for x in prev)
    return "M1 bearish MSS" if cur["close"] < swing and cur["close"] < cur["open"] else None


def build_atr_series(bars, period=14):
    """O(n) rolling ATR series; value at i uses candles only through i."""
    tr = [None] * len(bars)
    for i in range(1, len(bars)):
        cur, pc = bars[i], bars[i-1]["close"]
        tr[i] = max(cur["high"]-cur["low"], abs(cur["high"]-pc), abs(cur["low"]-pc))
    out = [None] * len(bars)
    for i in range(period, len(bars)):
        vals = tr[i-period+1:i+1]
        if all(x is not None for x in vals):
            out[i] = sum(vals) / period
    return out


def atr_regime_ok(values, index):
    """Reject volatility spikes above 2.5x the trailing median ATR."""
    if index < 120 or values[index] is None:
        return False
    prior = [x for x in values[max(0,index-100):index] if x is not None]
    if len(prior) < 30:
        return False
    median = statistics.median(prior)
    return median > 0 and values[index] <= 2.5 * median


def directional_m5_alignment(m5, direction):
    if len(m5) < 3:
        return False
    cur, prev = m5[-1], m5[-2]
    if direction == "BUY":
        return cur["close"] > prev["close"] and cur["close"] > cur["open"]
    return cur["close"] < prev["close"] and cur["close"] < cur["open"]


def replay(histories, cost_r):
    m5, m1 = histories["M5"], histories["M1"]
    m1_ends = [x["_end"] for x in m1]
    m15_ends = [x["_end"] for x in histories["M15"]]
    tf_ends = {tf:[x["_end"] for x in histories[tf]] for tf in ZONE_TFS if tf != "M15"}
    plain = {tf:bt.strip_internal(histories[tf]) for tf in histories}
    atr_values = build_atr_series(plain["M5"])
    variants = {
        "A_M5_required_M1_entry_refinement": {
            "trades":[], "seen":set(), "last_exit":-1,
            "diagnostics":{"setups":0,"m5_confirmations":0,"m1_refinements":0,"signals":0}},
        "B_M1_MSS_alternative_with_M5_alignment": {
            "trades":[], "seen":set(), "last_exit":-1,
            "diagnostics":{"setups":0,"m5_confirmations":0,"m1_mss_signals":0,"signals":0}},
    }
    for i in range(120,len(m5)-1):
        decision=m5[i]["_end"]
        price=m5[i]["close"]
        m5_prefix=plain["M5"][:i+1]
        m1_prefix=plain["M1"][:bisect.bisect_right(m1_ends,decision)]
        if not atr_regime_ok(atr_values,i):
            continue
        zones=[]
        for tf in ZONE_TFS:
            if tf=="M15":
                prefix=plain["M15"][:bisect.bisect_right(m15_ends,decision)]
            else:
                prefix=bt.strip_internal(histories[tf][:bisect.bisect_right(tf_ends[tf],decision)])
            if len(prefix)>=35:
                zones.extend(live.detect_zones(prefix,tf))
        if not zones:
            continue
        candidates=[z for z in bt.score_candidates(zones,price) if z["score"]>=7]
        if not candidates:
            continue
        best=candidates[0]
        direction="BUY" if best["direction"]=="DEMAND" else "SELL"
        zone_key=(best["tf"],best["direction"],round(best["low"],4),round(best["high"],4),best["created"])
        m5_confirm=live.confirmation(m5_prefix,best)
        m1_mss=mss_confirmation(m1_prefix,best)
        for name,state in variants.items():
            diag=state["diagnostics"]
            diag["setups"]+=1
            if m5_confirm:
                diag["m5_confirmations"]+=1
            if m1_mss:
                diag["m1_mss_signals"]=diag.get("m1_mss_signals",0)+1
            if name.startswith("A_"):
                # M5 confirmation is mandatory; M1 can only refine its entry.
                if not m5_confirm:
                    continue
                entry=m5_prefix[-1]["close"]
                entry_time=m5_prefix[-1]["time"]
                note=m5_confirm
                if m1_mss and directional_m5_alignment(m5_prefix,direction):
                    entry=m1_prefix[-1]["close"]
                    entry_time=m1_prefix[-1]["time"]
                    note+=" + M1 MSS entry refinement"
                    diag["m1_refinements"]+=1
            else:
                # M1 MSS can replace the M5 candle pattern only if M5 direction agrees.
                if not m1_mss or not directional_m5_alignment(m5_prefix,direction):
                    continue
                entry=m1_prefix[-1]["close"]
                entry_time=m1_prefix[-1]["time"]
                note=m1_mss+" + M5 directional alignment"
            if zone_key in state["seen"]:
                continue
            state["seen"].add(zone_key)
            diag["signals"]+=1
            if i<=state["last_exit"]:
                continue
            result=bt.simulate_trade(m5_prefix+plain["M5"][i+1:],i,direction,entry,best["stop"],cost_r=cost_r)
            if result is None:
                continue
            state["trades"].append({"variant":name,"signal_time":entry_time,"direction":direction,
                "zone_tf":best["tf"],"score":best["score"],"zone_low":best["low"],
                "zone_high":best["high"],"confirmation":note,"entry":entry,"stop":best["stop"],**result})
            state["last_exit"]=result["exit_index"]
    return variants


def replay_original(histories,cost_r,start_time,end_time):
    """Original live rules replayed on the exact M5 sample's calendar window."""
    m15_all=histories["M15"]
    m15=[b for b in m15_all if start_time<=b["_end"]<=end_time]
    tf_ends={tf:[x["_end"] for x in histories[tf]] for tf in ZONE_TFS if tf!="M15"}
    plain=bt.strip_internal(m15)
    trades,seen,last_exit=[],set(),-1
    diag={"decision_bars":0,"setups_score_7_plus":0,"score_above_8":0,"confirmed_signals":0}
    for i in range(34,len(m15)-1):
        decision=m15[i]["_end"]
        zones=[]
        for tf in ZONE_TFS:
            if tf=="M15":
                prefix=plain[:i+1]
            else:
                prefix=bt.strip_internal(histories[tf][:bisect.bisect_right(tf_ends[tf],decision)])
            if len(prefix)>=35:
                zones.extend(live.detect_zones(prefix,tf))
        diag["decision_bars"]+=1
        if not zones:
            continue
        candidates=bt.score_candidates(zones,m15[i]["close"])
        if not candidates:
            continue
        best=candidates[0]
        if best["score"]>=7:
            diag["setups_score_7_plus"]+=1
        if best["score"]<=8:
            continue
        diag["score_above_8"]+=1
        confirm=live.confirmation(plain[:i+1],best)
        if not confirm:
            continue
        diag["confirmed_signals"]+=1
        key=(best["tf"],best["direction"],round(best["low"],4),round(best["high"],4),best["created"])
        if key in seen:
            continue
        seen.add(key)
        if i<=last_exit:
            continue
        direction="BUY" if best["direction"]=="DEMAND" else "SELL"
        result=bt.simulate_trade(plain,i,direction,m15[i]["close"],best["stop"],cost_r=cost_r)
        if result:
            trades.append({"signal_time":m15[i]["time"],"direction":direction,"zone_tf":best["tf"],
                "score":best["score"],"confirmation":confirm,**result})
            last_exit=result["exit_index"]
    return {"diagnostics":diag,"all":bt.summarize(trades),"trades":trades}


def main():
    cost=float(os.environ.get("SD_BACKTEST_COST_R","0.05"))
    histories,quality={},{}
    for interval,label,kind in HISTORY:
        histories[label],quality[label]=bt.fetch_history(interval,label,kind)
        print(f"{label}: {len(histories[label])} closed bars; {histories[label][0]['time']} .. {histories[label][-1]['time']}")
    variants=replay(histories,cost)
    baseline=replay_original(histories,cost,histories["M5"][0]["_start"],histories["M5"][-1]["_end"])
    OUT.mkdir(exist_ok=True)
    report={
        "purpose":"Research only; neither hybrid variant changes the live bot.",
        "data_source":"Twelve Data XAU/USD OHLC; not HFM bid/ask execution data.",
        "decision_time":"M5 candle close; only fully closed M1/M5 and higher-timeframe candles are used.",
        "opportunity_discovery":"Original Supply/Demand zones and scoring; score >=7 monitored setups are passed to independent confirmation gates.",
        "variant_A":"M5 confirmation mandatory; M1 MSS can refine entry timing but cannot create a signal.",
        "variant_B":"M1 MSS can replace M5 candle pattern only when M5 direction agrees.",
        "quality_gate":"M5 ATR regime rejects volatility spikes above 2.5x trailing median ATR; no volume confirmation because source lacks reliable spot-gold volume.",
        "cost_model":f"{cost:.4f}R fixed cost deduction per trade; proxy, not measured HFM spread/slippage.",
        "history":{tf:{"bars":len(histories[tf]),"first":histories[tf][0]["time"],"last":histories[tf][-1]["time"],"quality":quality[tf]} for tf in histories},
        "original_strategy_same_calendar_window":baseline,
        "variants":{},
        "limitations":["Twelve Data spot feed differs from HFM CFD feed.",
            "M1/M5 history is limited by provider output limits.",
            "No tick data; intrabar stop/target collisions use conservative stop-first handling.",
            "Fixed cost proxy is not actual spread, slippage, commission or swap.",
            "A low trade count or short out-of-sample period cannot establish durable profitability."]
    }
    for name,state in variants.items():
        trades=state["trades"]
        split=int(len(trades)*0.7)
        report["variants"][name]={"diagnostics":state["diagnostics"],"all":bt.summarize(trades),
            "in_sample_first_70pct":bt.summarize(trades[:split]),
            "out_of_sample_last_30pct":bt.summarize(trades[split:]),"trades":trades}
        with (OUT/f"{name}.csv").open("w",newline="",encoding="utf-8") as f:
            if trades:
                writer=csv.DictWriter(f,fieldnames=list(trades[0]))
                writer.writeheader()
                writer.writerows(trades)
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["variants"],ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
