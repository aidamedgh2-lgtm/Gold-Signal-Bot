import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ["TWELVEDATA_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
BASE_URL = "https://api.twelvedata.com/time_series"
STATE_FILE = Path("state.json")


def fetch_candles(interval, outputsize=260):
    params = urllib.parse.urlencode({
        "symbol": "XAU/USD",
        "interval": interval,
        "outputsize": outputsize,
        "timezone": "UTC",
        "apikey": API_KEY,
        "format": "JSON",
    })
    request = urllib.request.Request(
        f"{BASE_URL}?{params}",
        headers={"User-Agent": "Gold-Signal-Bot/1.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if "values" not in payload:
        message = payload.get("message") or payload.get("code") or str(payload)
        raise RuntimeError(f"Twelve Data ({interval}): {message}")

    candles = []
    for item in payload["values"]:
        candles.append({
            "time": item["datetime"],
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
        })
    candles.sort(key=lambda candle: candle["time"])

    # Exclude the newest bar because the provider may still be forming it.
    if len(candles) > 1:
        candles = candles[:-1]
    if len(candles) < 205:
        raise RuntimeError(f"Not enough closed {interval} candles: {len(candles)}")
    return candles


def ema(values, period):
    if len(values) < period:
        raise ValueError("Not enough values for EMA")
    alpha = 2.0 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1 - alpha) * result
    return result


def rsi(values, period=14):
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def atr(candles, period=14):
    true_ranges = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous_close = candles[index - 1]["close"]
        true_ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous_close),
            abs(current["low"] - previous_close),
        ))
    value = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        value = ((period - 1) * value + tr) / period
    return value


def trend(candles):
    closes = [candle["close"] for candle in candles]
    return {
        "close": closes[-1],
        "ema50": ema(closes, 50),
        "ema200": ema(closes, 200),
    }


def telegram_send(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")


def market_structure(candles, lookback=3, scan=80):
    """Describe recent confirmed swing structure from closed candles."""
    window = candles[-(scan + 2 * lookback + 1):]
    highs, lows = [], []
    for i in range(lookback, len(window) - lookback):
        high, low = window[i]["high"], window[i]["low"]
        left, right = window[i - lookback:i], window[i + 1:i + lookback + 1]
        if all(high > x["high"] for x in left + right):
            highs.append(high)
        if all(low < x["low"] for x in left + right):
            lows.append(low)
    last_high = highs[-1] if highs else None
    last_low = lows[-1] if lows else None
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            label = "قمم وقيعان صاعدة"
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            label = "قمم وقيعان هابطة"
        else:
            label = "هيكل متداخل / عرضي"
    else:
        label = "بيانات الهيكل غير كافية"
    return {"label": label, "last_swing_high": last_high, "last_swing_low": last_low}


def ict_candidate(candles, current_atr):
    """Rule-based ICT-inspired proxy: liquidity sweep, MSS, then FVG.

    This uses OHLC candles only. It is not a complete ICT model and has no
    order-book, broker-tick, or institutional execution data.
    """
    if len(candles) < 100:
        return None

    prior = candles[:-12]
    recent = candles[-12:]
    prior_structure = market_structure(prior, lookback=2, scan=80)
    swing_high = prior_structure["last_swing_high"]
    swing_low = prior_structure["last_swing_low"]
    if swing_high is None or swing_low is None:
        return None

    bullish_sweep = None
    bearish_sweep = None
    for i, candle in enumerate(recent):
        if candle["low"] < swing_low and candle["close"] > swing_low:
            bullish_sweep = (i, candle["low"])
        if candle["high"] > swing_high and candle["close"] < swing_high:
            bearish_sweep = (i, candle["high"])

    candidates = []
    for direction, sweep, mss_level in (
        ("BUY", bullish_sweep, max(x["high"] for x in prior[-8:])),
        ("SELL", bearish_sweep, min(x["low"] for x in prior[-8:])),
    ):
        if sweep is None:
            continue
        sweep_index, sweep_extreme = sweep
        post_sweep = recent[sweep_index + 1:]
        if not post_sweep:
            continue

        if direction == "BUY":
            mss = any(x["close"] > mss_level for x in post_sweep)
        else:
            mss = any(x["close"] < mss_level for x in post_sweep)
        if not mss:
            continue

        # Find a recent three-candle Fair Value Gap formed after the sweep.
        fvg = None
        for j in range(max(sweep_index + 1, len(recent) - 6), len(recent)):
            absolute_index = len(candles) - 12 + j
            if absolute_index < 2:
                continue
            first = candles[absolute_index - 2]
            third = candles[absolute_index]
            if direction == "BUY" and third["low"] > first["high"]:
                fvg = (first["high"], third["low"])
            elif direction == "SELL" and third["high"] < first["low"]:
                fvg = (third["high"], first["low"])

        if fvg is None:
            continue

        zone_low, zone_high = min(fvg), max(fvg)
        entry = (zone_low + zone_high) / 2
        # Reject stale or distant FVGs; a setup must remain near the current price.
        if abs(candles[-1]["close"] - entry) > 1.5 * current_atr:
            continue

        stop = sweep_extreme - 0.20 * current_atr if direction == "BUY" else sweep_extreme + 0.20 * current_atr
        risk = abs(entry - stop)
        if risk <= 0 or risk > 2.5 * current_atr:
            continue
        candidates.append({
            "strategy": "ICT",
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "risk": risk,
            "zone_low": zone_low,
            "zone_high": zone_high,
            "score": 80,
            "reasons": [
                "تم رصد Liquidity Sweep لمستوى Swing سابق",
                "حدث Market Structure Shift (MSS) بعد سحب السيولة",
                "تكوّنت منطقة Fair Value Gap (FVG) بعد التحول",
            ],
        })

    return max(candidates, key=lambda x: x["score"]) if candidates else None


def build_technical_candidate(direction, entry, atr_value, reasons):
    if not direction:
        return None
    risk = 1.5 * atr_value
    stop = entry - risk if direction == "BUY" else entry + risk
    return {
        "strategy": "Technical",
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "risk": risk,
        "score": 76,
        "reasons": reasons,
    }


def classify_trend(data):
    if data["ema50"] > data["ema200"] and data["close"] > data["ema50"]:
        return "صاعد"
    if data["ema50"] < data["ema200"] and data["close"] < data["ema50"]:
        return "هابط"
    return "محايد أو تصحيح"


def fibonacci_analysis(candles, current_atr, lookback=3, scan=80):
    """Return Fibonacci retracement levels from the latest confirmed swing.
    Informational only: this function does not alter live trade selection.
    """
    window = candles[-(scan + 2 * lookback + 1):]
    highs, lows = [], []
    for i in range(lookback, len(window) - lookback):
        high, low = window[i]["high"], window[i]["low"]
        neighbors = window[i - lookback:i] + window[i + 1:i + lookback + 1]
        if all(high > x["high"] for x in neighbors): highs.append((i, high))
        if all(low < x["low"] for x in neighbors): lows.append((i, low))
    label = market_structure(candles, lookback=lookback, scan=scan)["label"]
    direction = "BUY" if label == "قمم وقيعان صاعدة" else ("SELL" if label == "قمم وقيعان هابطة" else None)
    if direction == "BUY":
        pairs = [(lo, hi) for lo in lows for hi in highs if lo[0] < hi[0]]
        if not pairs: return {"available": False}
        lo, hi = max(pairs, key=lambda pair: pair[1][0])
        swing_low, swing_high = lo[1], hi[1]
        span = swing_high - swing_low
        levels = {r: swing_high - span * r for r in (0.382, 0.500, 0.618, 0.705, 0.786)}
    elif direction == "SELL":
        pairs = [(hi, lo) for hi in highs for lo in lows if hi[0] < lo[0]]
        if not pairs: return {"available": False}
        hi, lo = max(pairs, key=lambda pair: pair[1][0])
        swing_high, swing_low = hi[1], lo[1]
        span = swing_high - swing_low
        levels = {r: swing_low + span * r for r in (0.382, 0.500, 0.618, 0.705, 0.786)}
    else:
        return {"available": False}
    if span <= 0: return {"available": False}
    price = candles[-1]["close"]
    ratio, level_price = min(levels.items(), key=lambda item: abs(price - item[1]))
    tolerance = 0.15 * current_atr
    return {"available": True, "direction": direction, "levels": levels,
            "nearest_ratio": ratio, "nearest_price": level_price,
            "distance": abs(price - level_price),
            "classic_near": any(abs(price - levels[x]) <= tolerance for x in (0.382, 0.500, 0.618, 0.786)),
            "705_near": abs(price - levels[0.705]) <= tolerance}

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    h4 = fetch_candles("4h")
    h1 = fetch_candles("1h")
    m15 = fetch_candles("15min")

    h4_trend = trend(h4)
    h1_trend = trend(h1)
    closes = [candle["close"] for candle in m15]
    last = m15[-1]
    last_rsi = rsi(closes)
    last_atr = atr(m15)
    m15_ema50 = ema(closes, 50)
    structure = market_structure(m15)
    fib = fibonacci_analysis(m15, last_atr)
    if not math.isfinite(last_atr) or last_atr <= 0:
        raise RuntimeError("Invalid ATR; refusing to create a signal")

    state = load_state()
    now = datetime.now(timezone.utc)
    today_utc = now.strftime("%Y-%m-%d")

    # The workflow runs every 15 minutes. Send one daily diagnostics report
    # after 20:00 UTC (21:00 in Algeria, UTC+1); delayed runs still send it.
    if now.hour >= 20 and state.get("daily_report_date") != today_utc:
        m15_status = "فوق EMA50" if last["close"] > m15_ema50 else "تحت أو عند EMA50"
        h4_status = classify_trend(h4_trend)
        h1_status = classify_trend(h1_trend)
        if last_rsi > 55:
            momentum = "يميل للصعود"
        elif last_rsi < 45:
            momentum = "يميل للهبوط"
        else:
            momentum = "محايد"

        report = (
            "📊 التقرير اليومي — GOLD SIGNAL BOT\\n"
            f"التاريخ: {today_utc} (UTC)\\n\\n"
            "التحليل الفني: بيانات الأسعار والمؤشرات متاحة من Twelve Data\\n"
            f"• H4: {h4_status}\\n"
            f"• H1: {h1_status}\\n"
            f"• M15: {m15_status}\\n"
            f"• هيكل M15: {structure['label']}\\n"
            f"• RSI(14): {last_rsi:.1f} — الزخم {momentum}\\n"
            f"• EMA50 M15: {m15_ema50:.2f} | ATR(14): {last_atr:.2f}\\n"
            f"• آخر إغلاق M15: {last['close']:.2f} (سعر مرجعي XAU/USD Spot)\\n\\n"
            + (f"• Fibonacci M15: أقرب مستوى {fib['nearest_ratio']:.3f} عند {fib['nearest_price']:.2f} | المسافة {fib['distance']:.2f} | تقليدي قريب: {'نعم' if fib['classic_near'] else 'لا'} | 0.705 قريب: {'نعم' if fib['705_near'] else 'لا'}\\n" if fib.get('available') else '• Fibonacci M15: لا يوجد Swing واضح صالح للحساب\\n') +
            "التحليل الأساسي: غير مدمج — لا توجد تغذية أخبار أو بيانات اقتصادية.\\n"
            "التحليل الزمني: غير مدمج — لا يوجد نموذج مستقل لدورات/توقيت السوق.\\n"
            "التحليل الموجي: غير مدمج — لم يتم احتساب موجات إليوت.\\n"
            "Bookmap / Order Flow: غير متصل — لا تتوفر بيانات عمق السوق والأوامر.\\n\\n"
            "القرار: هذا تقرير حالة وليس إشارة تداول. لا تنفذي صفقة بناءً عليه."
        )
        telegram_send(report)
        state["daily_report_date"] = today_utc
        save_state(state)
        print(f"Daily diagnostics report sent for {today_utc}")

    technical_direction = None
    technical_reasons = []
    if (h4_trend["ema50"] > h4_trend["ema200"]
            and h4_trend["close"] > h4_trend["ema50"]
            and h1_trend["ema50"] > h1_trend["ema200"]
            and h1_trend["close"] > h1_trend["ema50"]
            and last["close"] > m15_ema50
            and structure["label"] == "قمم وقيعان صاعدة"
            and last["close"] > m15[-2]["high"]
            and 50 <= last_rsi <= 68):
        technical_direction = "BUY"
        technical_reasons = ["اتجاه H4 صاعد", "تأكيد H1 صاعد", "هيكل M15 يصنع قمماً وقيعاناً صاعدة", "إغلاق M15 فوق EMA50 وفوق قمة الشمعة السابقة", "RSI ضمن نطاق الزخم الصاعد"]
    elif (h4_trend["ema50"] < h4_trend["ema200"]
            and h4_trend["close"] < h4_trend["ema50"]
            and h1_trend["ema50"] < h1_trend["ema200"]
            and h1_trend["close"] < h1_trend["ema50"]
            and last["close"] < m15_ema50
            and structure["label"] == "قمم وقيعان هابطة"
            and last["close"] < m15[-2]["low"]
            and 32 <= last_rsi <= 50):
        technical_direction = "SELL"
        technical_reasons = ["اتجاه H4 هابط", "تأكيد H1 هابط", "هيكل M15 يصنع قمماً وقيعاناً هابطة", "إغلاق M15 تحت EMA50 وتحت قاع الشمعة السابقة", "RSI ضمن نطاق الزخم الهابط"]

    technical = build_technical_candidate(
        technical_direction, last["close"], last_atr, technical_reasons
    )
    ict = ict_candidate(m15, last_atr)

    if technical and ict and technical["direction"] != ict["direction"]:
        print("NO TRADE: ICT and Technical strategies conflict.")
        return

    if technical and ict:
        selected = dict(technical)
        selected["score"] = 90
        selected["strategy"] = "ICT + Technical (confluence)"
        selected["reasons"] = technical["reasons"] + ict["reasons"]
        # Use the ICT-defined risk and entry zone when both strategies agree.
        selected["entry"] = ict["entry"]
        selected["stop"] = ict["stop"]
        selected["risk"] = ict["risk"]
        selected["zone_low"] = ict["zone_low"]
        selected["zone_high"] = ict["zone_high"]
    elif ict:
        selected = ict
    elif technical:
        selected = technical
    else:
        print("NO TRADE: neither strategy produced a qualifying setup.")
        return

    if selected["score"] < 75:
        print("NO TRADE: selected setup did not meet the quality threshold.")
        return

    direction = selected["direction"]
    entry = selected["entry"]
    stop = selected["stop"]
    risk = selected["risk"]
    tp1 = entry + 1.5 * risk if direction == "BUY" else entry - 1.5 * risk
    tp2 = entry + 2.5 * risk if direction == "BUY" else entry - 2.5 * risk
    tp3 = entry + 3.0 * risk if direction == "BUY" else entry - 3.0 * risk

    candle_time = last["time"]
    if state.get("last_signal_candle") == candle_time:
        print("Duplicate signal candle; nothing sent.")
        return

    ict_status = f"{ict['direction']} (درجة {ict['score']}/100)" if ict else "لا توجد فرصة مستوفية للشروط"
    technical_status = f"{technical['direction']} (درجة {technical['score']}/100)" if technical else "لا توجد فرصة مستوفية للشروط"
    zone_text = (
        f"منطقة FVG: {selected['zone_low']:.2f} — {selected['zone_high']:.2f}\\n"
        if "zone_low" in selected else ""
    )

    message = (
        f"📈 تقرير فرصة تداول — {direction}\\n"
        "الأداة: XAU/USD Spot (قد يختلف عن سعر HFM)\\n"
        f"وقت شمعة M15 المغلقة: {candle_time} UTC\\n\\n"
        "مقارنة الاستراتيجيات المستقلة:\\n"
        f"• ICT: {ict_status}\\n"
        f"• Technical: {technical_status}\\n"
        f"الاستراتيجية المختارة: {selected['strategy']}\\n"
        f"قوة الإعداد التقديرية: {selected['score']}/100 (ليست نسبة نجاح)\\n\\n"
        "التحليل الفني العام:\\n"
        f"• H4: {classify_trend(h4_trend)} | H1: {classify_trend(h1_trend)}\\n"
        f"• هيكل M15: {structure['label']}\\n"
        f"• EMA50: {m15_ema50:.2f} | RSI(14): {last_rsi:.1f} | ATR(14): {last_atr:.2f}\\n"
        + (f"• Fibonacci: أقرب مستوى {fib['nearest_ratio']:.3f} عند {fib['nearest_price']:.2f} | المسافة {fib['distance']:.2f} | تقليدي قريب: {'نعم' if fib['classic_near'] else 'لا'} | 0.705 قريب: {'نعم' if fib['705_near'] else 'لا'}\\n" if fib.get('available') else '• Fibonacci: لا يوجد Swing واضح صالح للحساب\\n')
        + zone_text +
        f"Entry: {entry:.2f}\\n"
        f"SL: {stop:.2f}\\n"
        f"TP1: {tp1:.2f} | R:R = 1:1.5\\n"
        f"TP2: {tp2:.2f} | R:R = 1:2.5\\n"
        f"TP3: {tp3:.2f} | R:R = 1:3.0\\n"
        "أسباب الإعداد: " + "؛ ".join(selected["reasons"]) + "\\n"
        "التحليل الأساسي والأخبار: غير مدمج.\\n"
        "Bookmap / Order Flow: غير متاح؛ بيانات عمق السوق غير موصولة.\\n"
        "ملاحظة: ICT هنا نموذج آلي تقريبي مبني على OHLC، وليس تطبيقاً كاملاً لكل قواعد ICT. الإشارة غير مختبرة ربحياً؛ لا تنفذيها على حساب حقيقي."
    )
    telegram_send(message)
    state["last_signal_candle"] = candle_time
    state["direction"] = direction
    save_state(state)
    print(f"Signal sent for closed M15 candle {candle_time}")

if __name__ == "__main__":
    main()
