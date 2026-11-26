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


def classify_trend(data):
    if data["ema50"] > data["ema200"] and data["close"] > data["ema50"]:
        return "صاعد"
    if data["ema50"] < data["ema200"] and data["close"] < data["ema50"]:
        return "هابط"
    return "محايد أو تصحيح"


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
    if not math.isfinite(last_atr) or last_atr <= 0:
        raise RuntimeError("Invalid ATR; refusing to create a signal")

    state = load_state()
    now = datetime.now(timezone.utc)
    today_utc = now.strftime("%Y-%m-%d")

    # The workflow runs every 15 minutes. Send one daily diagnostics report
    # after 20:00 UTC (21:00 in Algeria, UTC+1); delayed runs still send it.
    if now.hour >= 20 and state.get("daily_report_date") != today_utc:
        m15_ema50 = ema(closes, 50)
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
            "📊 التقرير اليومي — GOLD SIGNAL BOT\n"
            f"التاريخ: {today_utc} (UTC)\n\n"
            "التحليل الفني: متاح من بيانات Twelve Data\n"
            f"• H4: {h4_status}\n"
            f"• H1: {h1_status}\n"
            f"• M15: {m15_status}\n"
            f"• RSI(14): {last_rsi:.1f} — الزخم {momentum}\n"
            f"• آخر إغلاق M15: {last['close']:.2f} (سعر مرجعي XAU/USD Spot)\n\n"
            "التحليل الأساسي: غير مدمج حالياً — لا توجد تغذية أخبار/بيانات اقتصادية في البوت.\n"
            "التحليل الزمني: غير مدمج — لا يوجد نموذج مستقل لدورات/توقيت السوق.\n"
            "التحليل الموجي: غير مدمج — لم يتم احتساب موجات إليوت.\n"
            "Bookmap وتدفق الأوامر: غير متصل — لا تتوفر بيانات عمق السوق/الأوامر.\n\n"
            "القرار الآلي: هذا تقرير حالة وليس إشارة تداول. لا تنفذي صفقة بناءً عليه."
        )
        telegram_send(report)
        state["daily_report_date"] = today_utc
        save_state(state)
        print(f"Daily diagnostics report sent for {today_utc}")

    direction = None
    reasons = []
    if (h4_trend["ema50"] > h4_trend["ema200"]
            and h4_trend["close"] > h4_trend["ema50"]
            and h1_trend["ema50"] > h1_trend["ema200"]
            and h1_trend["close"] > h1_trend["ema50"]
            and last["close"] > ema(closes, 50)
            and 50 <= last_rsi <= 68):
        direction = "BUY"
        reasons = ["اتجاه H4 صاعد", "تأكيد H1 صاعد", "إغلاق M15 فوق EMA50", "RSI ضمن نطاق الزخم الصاعد"]
    elif (h4_trend["ema50"] < h4_trend["ema200"]
            and h4_trend["close"] < h4_trend["ema50"]
            and h1_trend["ema50"] < h1_trend["ema200"]
            and h1_trend["close"] < h1_trend["ema50"]
            and last["close"] < ema(closes, 50)
            and 32 <= last_rsi <= 50):
        direction = "SELL"
        reasons = ["اتجاه H4 هابط", "تأكيد H1 هابط", "إغلاق M15 تحت EMA50", "RSI ضمن نطاق الزخم الهابط"]

    if not direction:
        print("NO TRADE: multi-timeframe conditions are not aligned.")
        return

    candle_time = last["time"]
    if state.get("last_signal_candle") == candle_time:
        print("Duplicate signal candle; nothing sent.")
        return

    entry = last["close"]
    risk = 1.5 * last_atr
    if direction == "BUY":
        stop = entry - risk
        tp1 = entry + 1.5 * risk
        tp2 = entry + 2.5 * risk
    else:
        stop = entry + risk
        tp1 = entry - 1.5 * risk
        tp2 = entry - 2.5 * risk

    message = (
        f"تنبيه تداول تجريبي — {direction}\n"
        f"الأداة: XAU/USD Spot (ليس سعراً مضموناً مطابقاً لـ HFM)\n"
        f"وقت شمعة M15 المغلقة: {candle_time} UTC\n"
        f"السعر المرجعي: {entry:.2f}\n"
        f"وقف الخسارة النظري: {stop:.2f}\n"
        f"الهدف الأول: {tp1:.2f}\n"
        f"الهدف الثاني: {tp2:.2f}\n"
        f"RSI(14): {last_rsi:.1f}\n"
        f"الأسباب: " + "؛ ".join(reasons) + "\n"
        "ملاحظة: إشارة آلية أولية للاختبار فقط، وليست توصية مالية. تحققي من السعر والسبريد لدى وسيطك قبل أي قرار."
    )
    telegram_send(message)
    state["last_signal_candle"] = candle_time
    state["direction"] = direction
    save_state(state)
    print(f"Signal sent for closed M15 candle {candle_time}")

if __name__ == "__main__":
    main()
