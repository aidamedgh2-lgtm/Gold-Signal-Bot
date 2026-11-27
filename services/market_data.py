"""Twelve Data market-data adapter. Credentials remain in GitHub Actions secrets."""
import json
import math
import urllib.parse
import urllib.request


API = "https://api.twelvedata.com/time_series"


def fetch_twelvedata_candles(interval, api_key, symbol="XAU/USD", outputsize=260):
    if not api_key:
        raise RuntimeError("TWELVEDATA_API_KEY is missing")
    params = urllib.parse.urlencode({
        "symbol": symbol, "interval": interval, "outputsize": outputsize,
        "timezone": "UTC", "apikey": api_key, "format": "JSON",
    })
    request = urllib.request.Request(
        API + "?" + params, headers={"User-Agent": "Gold-SD-Bot/1.0"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "values" not in payload:
        raise RuntimeError(str(payload.get("message") or payload.get("code") or payload))
    bars = [{
        "time": item["datetime"],
        **{key: float(item[key]) for key in ("open", "high", "low", "close")},
    } for item in payload["values"]]
    bars.sort(key=lambda bar: bar["time"])
    # Exclude the newest candle because the provider may still be forming it.
    if len(bars) > 1:
        bars = bars[:-1]
    if len(bars) < 35:
        raise RuntimeError(f"Insufficient data: {interval} ({len(bars)} candles)")
    for bar in bars:
        if not all(math.isfinite(bar[key]) for key in ("open", "high", "low", "close")):
            raise RuntimeError("Invalid non-finite OHLC value")
        if (bar["high"] < max(bar["open"], bar["close"], bar["low"])
                or bar["low"] > min(bar["open"], bar["close"], bar["high"])):
            raise RuntimeError("Invalid OHLC ordering")
    return bars
