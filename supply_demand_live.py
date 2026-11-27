"""Supply & Demand XAU/USD alert engine.
All visual concepts are explicit OHLC/ATR proxies; no broker execution.
"""
import json
import math
import datetime as dt
import os
import urllib.parse
import urllib.request
from pathlib import Path

from services.market_data import fetch_twelvedata_candles
from services.telegram import send_telegram_message
from services.vision_review import assess_candidate
from services.chart_detector import detect_visual_zones

API = "https://api.twelvedata.com/time_series"
SYMBOL = "XAU/USD"
# إعدادات قابلة للتعديل
TIMEFRAMES = [("1month", "MN1"), ("1week", "W1"), ("1day", "D1"),
              ("4h", "H4"), ("1h", "H1"), ("15min", "M15")]
OUTPUTSIZE = 260
BASE_MIN, BASE_MAX = 1, 4
SCAN_BARS = 180
ROCKET_ATR, STAIR_ATR = 2.5, 1.2
ZONE_MATCH_ATR = 0.15
MAX_NEAR_ATR = 1.5
STOP_BUFFER_ATR = 0.20
MIN_CONFIRM_BODY = 0.65
STATE_FILE = Path("state.json")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4.1-mini").strip()
FINZDATA_API_KEY = os.environ.get("FINZDATA_API_KEY", "").strip()
FINZDATA_CONTEXT_ENABLED = os.environ.get("FINZDATA_CONTEXT_ENABLED", "false").lower() == "true"


def send(text):
    send_telegram_message(text, BOT_TOKEN, CHAT_ID)


def fetch(interval):
    return fetch_twelvedata_candles(interval, API_KEY, SYMBOL, OUTPUTSIZE)


def atr(bars, period=14):
    trs = []
    for i in range(1, len(bars)):
        b, pc = bars[i], bars[i-1]["close"]
        trs.append(max(b["high"]-b["low"], abs(b["high"]-pc), abs(b["low"]-pc)))
    if len(trs) < period:
        return None
    value = sum(trs[-period:]) / period
    return value if value > 0 else None


def detect_zones(bars, tf):
    """Fail closed: the former ATR/OHLC proxy is not the PDF's visual zone method.

    Do not generate candidate zones until a chart-first detector has passed the
    PDF golden-case benchmark. Returning no zones is intentional and prevents
    proxy-derived candidates from being presented as strategy-compliant.
    """
    return []


def overlaps(a, b):
    gap = max(0.0, max(a["low"], b["low"]) - min(a["high"], b["high"]))
    tolerance = max((a["high"]-a["low"])*0.5,
                    (b["high"]-b["low"])*0.5,
                    ZONE_MATCH_ATR*max(a["atr"], b["atr"]))
    return gap <= tolerance


def confirmation(bars, zone):
    """شمعة M15 مغلقة: ابتلاعية أو إغلاق قوي باتجاه الارتداد، مع لمس المنطقة."""
    if len(bars) < 3:
        return None
    prev, cur = bars[-2], bars[-1]
    touched_cur = cur["low"] <= zone["high"] and cur["high"] >= zone["low"]
    touched_prev = prev["low"] <= zone["high"] and prev["high"] >= zone["low"]
    touched = touched_cur or touched_prev
    if not touched:
        return None
    rng = max(cur["high"]-cur["low"], 1e-9)
    body = abs(cur["close"]-cur["open"])
    if zone["direction"] == "DEMAND":
        engulf = (cur["close"] > cur["open"] and prev["close"] < prev["open"] and
                  cur["open"] <= prev["close"] and cur["close"] >= prev["open"])
        strong = cur["close"] > cur["open"] and body/rng >= MIN_CONFIRM_BODY and (cur["high"]-cur["close"])/rng <= 0.20
    else:
        engulf = (cur["close"] < cur["open"] and prev["close"] > prev["open"] and
                  cur["open"] >= prev["close"] and cur["close"] <= prev["open"])
        strong = cur["close"] < cur["open"] and body/rng >= MIN_CONFIRM_BODY and (cur["close"]-cur["low"])/rng <= 0.20
    return "Engulfing" if engulf else ("Strong Candle Close" if strong else None)



def comex_daily_context():
    """Non-directional COMEX participation context; never changes signal scoring."""
    if not FINZDATA_CONTEXT_ENABLED:
        return "COMEX: اختبار السياق غير مفعّل في التشغيل الحي."
    if not FINZDATA_API_KEY:
        return "COMEX: مفتاح FinzData غير موجود؛ لم تُستخدم بيانات الحجم."
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=30)
    params = urllib.parse.urlencode({
        "root": "GC", "continuous": "true",
        "start": start.isoformat(), "end": today.isoformat()
    })
    req = urllib.request.Request(
        "https://api.finzdata.com/v1/futures/daily?" + params,
        headers={"X-API-Key": FINZDATA_API_KEY, "Accept": "application/json",
                 "User-Agent": "Gold-SD-Bot/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("data", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return "COMEX: تعذر قراءة بنية البيانات اليومية."
        valid = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                day = dt.date.fromisoformat(str(row.get("date", ""))[:10])
                volume = float(row.get("volume"))
                if math.isfinite(volume) and volume > 0:
                    valid.append((day, volume, row.get("open_interest")))
            except (TypeError, ValueError):
                continue
        valid.sort(key=lambda item: item[0])
        if len(valid) < 6:
            return f"COMEX: بيانات حجم غير كافية ({len(valid)} جلسات صالحة)."
        latest_day, latest_volume, latest_oi = valid[-1]
        age = (today - latest_day).days
        if age > 4:
            return f"COMEX: آخر بيانات حجم تعود إلى {latest_day.isoformat()}؛ قديمة، ولا تستخدم للتأكيد."
        prior = valid[-21:-1]
        if not prior:
            return "COMEX: لا توجد جلسات سابقة كافية للمقارنة."
        avg_volume = sum(x[1] for x in prior) / len(prior)
        ratio = latest_volume / avg_volume if avg_volume > 0 else 0
        volume_state = ("أعلى من متوسط 20 جلسة" if ratio >= 1.15 else
                        ("أقل من متوسط 20 جلسة" if ratio <= 0.85 else
                         "قريب من متوسط 20 جلسة"))
        oi_text = "Open Interest غير متاح أو غير صالح للمقارنة"
        try:
            latest_oi_value = float(latest_oi)
            previous_oi_value = float(prior[-1][2])
            # Zero/negative OI values are not accepted for percentage comparison.
            if (math.isfinite(latest_oi_value) and math.isfinite(previous_oi_value)
                    and latest_oi_value > 0 and previous_oi_value > 0):
                oi_change = latest_oi_value - previous_oi_value
                oi_pct = oi_change / previous_oi_value * 100
                oi_text = f"Open Interest {'ارتفع' if oi_change > 0 else ('انخفض' if oi_change < 0 else 'لم يتغير')} ({oi_pct:+.2f}%)"
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        return (f"COMEX GC اليومي ({latest_day.isoformat()}): Volume {latest_volume:,.0f} "
                f"({volume_state}؛ {ratio:.2f}x مقابل متوسط {len(prior)} جلسة)، {oi_text}. "
                "معلومة سياقية غير اتجاهية وليست إشارة BUY/SELL.")
    except Exception as exc:
        print(f"FinzData context unavailable: {exc}")
        return "COMEX: تعذر جلب البيانات الآن؛ التحليل الفني مستمر دون هذا العامل."

def main():
    if not OPENAI_API_KEY:
        print("إيقاف آمن: OPENAI_API_KEY غير موجود؛ لا يمكن تشغيل الكاشف البصري.")
        return
    data = {}
    observations = []
    # Chart-first extraction: AI reads calibrated candlestick charts; no ATR/OHLC proxy.
    for interval, label in TIMEFRAMES:
        try:
            bars = fetch(interval)
            data[label] = bars
            zones = detect_visual_zones(bars, label, OPENAI_API_KEY, OPENAI_VISION_MODEL)
            for item in zones:
                zone = {**item, "tf": label, "created": item["origin_start"]}
                visual = assess_candidate(bars, zone, OPENAI_API_KEY, OPENAI_VISION_MODEL)
                observations.append(
                    f'{label} {item["direction"]} {item["low"]:.2f}–{item["high"]:.2f} '
                    f'| departure={item["departure"]} | approach={visual["approach"]} '
                    f'| readability={visual["zone_readability"]} '
                    f'| confidence={item["confidence"]:.0%}/{visual["confidence"]:.0%} '
                    f'| evidence={item["evidence"]}'
                )
        except Exception as exc:
            print(f"{label}: visual scan unresolved: {exc}")
            return
    if not observations:
        print("لم يكتشف AI مناطق واضحة على الشارتات؛ لا تنبيه ولا صفقة.")
        return
    send(
        "👁️ رصد بصري أولي — XAU/USD\\n" + "\\n".join(observations[:12]) +
        "\\nهذه ملاحظات مناطق فقط. لم تُحسب نقاط الاستراتيجية /10، ولم تُثبت "
        "هوية المنطقة عبر الأطر أو الزيارات أو مدة D1/H4 أو R:R. لذلك لا توجد "
        "توصية دخول أو أمر معلّق. لا يوجد تنفيذ صفقات."
    )
    print(f"Visual observation completed: {len(observations)} candidate(s). "
          "Strategy scoring and trade alerts remain disabled.")
    return
    # كل فريم مستقل في جلب البيانات؛ تعذر أي فريم يعني عدم إصدار إشارة ناقصة.
    for interval, label in TIMEFRAMES:
        try:
            data[label] = fetch(interval)
        except Exception as exc:
            print(f"تعذر جلب {label}: {exc}. لن تصدر إشارة بهذه البيانات.")
            return
    all_zones = []
    for _, label in TIMEFRAMES:
        all_zones.extend(detect_zones(data[label], label))
    if not all_zones:
        print("لا توجد مناطق مرشحة.")
        return

    # AI vision reviews only chart-visible departure and approach geometry.
    # It does not decide direction, levels, score, or whether a trade is valid.
    tf_order = [x[1] for x in TIMEFRAMES]
    ranked = sorted(all_zones, key=lambda z: (tf_order.index(z["tf"]), z["created"]))
    review_lines = []
    for zone in ranked[:3]:
        label = f'{zone["tf"]} {zone["direction"]}: {zone["low"]:.2f}–{zone["high"]:.2f}'
        if not OPENAI_API_KEY:
            review_lines.append(label + " — AI غير مفعّل: OPENAI_API_KEY غير موجود.")
            continue
        try:
            visual = assess_candidate(
                data[zone["tf"]], zone, OPENAI_API_KEY, OPENAI_VISION_MODEL
            )
            confidence_pct = round(visual["confidence"] * 100)
            review_lines.append(
                label + f' — الانطلاق: {visual["departure"]}؛ '
                f'الاقتراب: {visual["approach"]}؛ وضوح المنطقة: {visual["zone_readability"]}؛ '
                f'ثقة النموذج: {confidence_pct}%'
                + f'؛ الدليل: {visual["evidence"]}'
                + (f'؛ سبب عدم الحسم: {visual["unknown_reason"]}' if visual["unknown_reason"] else "")
            )
        except Exception as exc:
            # Fail closed: an API/model/chart error must never create a score.
            print(f'Vision review unavailable for {label}: {exc}')
            review_lines.append(label + " — تعذر التقييم البصري؛ لا نقاط.")
    send(
        "👁️ مراجعة بصرية بالذكاء الاصطناعي — XAU/USD\n"
        + "\n".join(review_lines)
        + "\nالمرجع STRATEGY_REFERENCE.md أُرسل إلى نموذج الرؤية مع كل صورة. "
          "هذه ملاحظات بصرية أولية فقط. لم تُحسب علامة /10 ولم تصدر صفقة؛ "
          "بقية معايير PDF (التوافق الهرمي، الزيارات، المدة، R:R والهدف) "
          "ما زالت تحتاج ربطاً واختباراً حرفياً. لا يوجد تنفيذ أوامر."
    )
    print("Candidate chart vision review complete; trade scoring remains gated.")
    return

    comex_note = comex_daily_context()
    print(comex_note)
    m15 = data["M15"]
    price = m15[-1]["close"]
    candidates = []
    tf_order = [x[1] for x in TIMEFRAMES]
    for z in all_zones:
        # منطقة صالحة فقط إذا لم يكسرها السعر وبقي قريباً منها
        distance = max(z["low"]-price, 0, price-z["high"])
        if distance > MAX_NEAR_ATR*z["atr"]:
            continue
        if z["direction"] == "DEMAND" and price < z["low"]-0.15*z["atr"]:
            continue
        if z["direction"] == "SUPPLY" and price > z["high"]+0.15*z["atr"]:
            continue
        matches = [x for x in all_zones if x is not z and x["direction"] == z["direction"]
                   and x["tf"] != z["tf"] and overlaps(z,x)
                   and max(x["low"]-price, 0, price-x["high"]) <= MAX_NEAR_ATR*x["atr"]
                   and not ((x["direction"] == "DEMAND" and price < x["low"]-0.15*x["atr"]) or
                            (x["direction"] == "SUPPLY" and price > x["high"]+0.15*x["atr"]))]
        match_count = 1 + len({x["tf"] for x in matches})
        mtf_points = 2 if match_count >= 3 else (1 if match_count == 2 else 0)
        z["matches"] = sorted({x["tf"] for x in matches}, key=lambda t: tf_order.index(t))
        z["mtf_points"] = mtf_points
        z["score"] = (z["move_points"] + z["rr_points"] + mtf_points +
                      z["visit_points"] + z["duration_points"] + z["arrival_points"])
        candidates.append(z)
    if not candidates:
        print("لا توجد منطقة قريبة وصالحة حالياً.")
        return
    # الأولوية للأعلى نقاطاً ثم للفريم الأكبر
    candidates.sort(key=lambda z:(z["score"], -tf_order.index(z["tf"]), -z["move_atr"]), reverse=True)
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    seen = state.get("sd_seen", {})
    best = candidates[0]
    zone_id = f'{best["tf"]}:{best["direction"]}:{best["low"]:.2f}:{best["high"]:.2f}:{best["created"]}'
    score_lines = (f'الحركة: {best["move_points"]}/2 ({best["move_type"]})\n'
        f'R:R: {best["rr_points"]}/2 (تقريباً 1:{best["rr"]:.2f})\n'
        f'توافق الفريمات: {best["mtf_points"]}/2 ({", ".join(best["matches"]) or "لا يوجد"})\n'
        f'الزيارات: {best["visit_points"]}/2 (عدد الزيارات: {best["visits"]})\n'
        f'مدة القاعدة: {best["duration_points"]}/1 ({best["base_bars"]} شمعة)\n'
        f'الوصول: {best["arrival_points"]}/1\n')
    if best["score"] < 7:
        print(f'أفضل منطقة {best["score"]}/10؛ أقل من حد المراقبة.')
        return
    if best["score"] <= 8:
        if seen.get(zone_id) != "monitor":
            send(f'👁️ مراقبة منطقة {best["direction"]} — XAU/USD\nالفريم: {best["tf"]}\n'
                 f'المنطقة: {best["low"]:.2f} – {best["high"]:.2f}\nالتقييم: {best["score"]}/10\n'
                 + score_lines + 'لا توجد صفقة. ننتظر تحسن المنطقة/تأكيد الدخول.\n' + comex_note)
            seen[zone_id] = "monitor"
    else:
        confirm = confirmation(m15, best)
        # شمعة التأكيد M15 مطلوبة بعد أن يلمس السعر المنطقة.
        if confirm:
            entry = m15[-1]["close"]
            stop = best["stop"]
            risk = abs(entry-stop)
            if risk <= 0:
                print("مخاطرة غير صالحة؛ لا إشارة.")
                return
            tp1 = entry + (1.5*risk if best["direction"] == "DEMAND" else -1.5*risk)
            tp2 = entry + (2.5*risk if best["direction"] == "DEMAND" else -2.5*risk)
            tp3 = entry + (3.0*risk if best["direction"] == "DEMAND" else -3.0*risk)
            direction = "BUY" if best["direction"] == "DEMAND" else "SELL"
            signal_key = zone_id + ":" + m15[-1]["time"]
            if seen.get(zone_id) != "signal" and state.get("last_signal_key") != signal_key:
                send(f'🚨 توصية {direction} — XAU/USD\nالاستراتيجية: Supply & Demand\n'
                     f'المنطقة: {best["low"]:.2f} – {best["high"]:.2f} ({best["tf"]})\n'
                     f'شمعة التأكيد: {confirm} على M15\nالتقييم: {best["score"]}/10\n'
                     + score_lines +
                     f'Entry: {entry:.2f}\nSL: {stop:.2f}\nTP1: {tp1:.2f}\n'
                     f'TP2: {tp2:.2f}\nTP3: {tp3:.2f}\n'
                     + comex_note + '\nالدخول بعد إغلاق شمعة التأكيد؛ هذه إشارة تنبيه وليست أمراً منفذاً.')
                seen[zone_id] = "signal"
                state["last_signal_key"] = signal_key
        elif seen.get(zone_id) not in ("strong_wait", "signal"):
            send(f'⭐ منطقة قوية — XAU/USD\nالفريم: {best["tf"]}\n'
                 f'المنطقة: {best["low"]:.2f} – {best["high"]:.2f}\nالتقييم: {best["score"]}/10\n'
                 + score_lines + 'انتظار وصول السعر إلى المنطقة ثم شمعة تأكيد M15. لا دخول الآن.\n' + comex_note)
            seen[zone_id] = "strong_wait"
    state["sd_seen"] = seen
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f'Supply/Demand scan complete. Best zone score={best["score"]}/10, timeframe={best["tf"]}.')


if __name__ == "__main__":
    main()
