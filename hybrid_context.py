"""Deterministic, closed-candle hybrid market context for XAU/USD research.

This module reports evidence only. It does not issue trades, alter the original
10-point score, or claim that OHLC proxies are equivalent to discretionary chart
reading. Swing points are only exposed after the required right-hand bars close.
"""
from __future__ import annotations


def _valid_bars(bars):
    required = ("open", "high", "low", "close")
    for bar in bars:
        values = [bar.get(key) for key in required]
        if any(value is None for value in values):
            return False
        if not all(isinstance(value, (int, float)) for value in values):
            return False
        if not (bar["high"] >= max(bar["open"], bar["close"], bar["low"])
                and bar["low"] <= min(bar["open"], bar["close"], bar["high"])):
            return False
    return True


def confirmed_swings(bars, left=2, right=2):
    """Return pivot highs/lows confirmed using only bars available at this close."""
    if left < 1 or right < 1 or not _valid_bars(bars):
        return {"highs": [], "lows": []}
    highs, lows = [], []
    for i in range(left, len(bars) - right):
        window = bars[i-left:i+right+1]
        high = bars[i]["high"]
        low = bars[i]["low"]
        # Strict pivot: equal neighbouring highs/lows are not silently ranked.
        if all(high > b["high"] for j, b in enumerate(window) if j != left):
            highs.append({"index": i, "price": high})
        if all(low < b["low"] for j, b in enumerate(window) if j != left):
            lows.append({"index": i, "price": low})
    return {"highs": highs, "lows": lows}


def market_structure(bars, left=2, right=2):
    """Classify structure from the last two confirmed highs and lows."""
    swings = confirmed_swings(bars, left, right)
    highs, lows = swings["highs"], swings["lows"]
    if len(highs) < 2 or len(lows) < 2:
        return {"state": "unknown", "swing_highs": highs[-2:], "swing_lows": lows[-2:]}
    higher_high = highs[-1]["price"] > highs[-2]["price"]
    higher_low = lows[-1]["price"] > lows[-2]["price"]
    lower_high = highs[-1]["price"] < highs[-2]["price"]
    lower_low = lows[-1]["price"] < lows[-2]["price"]
    if higher_high and higher_low:
        state = "bullish"
    elif lower_high and lower_low:
        state = "bearish"
    else:
        state = "mixed"
    return {"state": state, "swing_highs": highs[-2:], "swing_lows": lows[-2:]}


def liquidity_sweep(bars, left=2, right=2):
    """Detect a closed candle taking a confirmed swing and closing back inside."""
    if not _valid_bars(bars) or len(bars) < left + right + 2:
        return None
    swings = confirmed_swings(bars[:-1], left, right)
    current = bars[-1]
    candidates = []
    if swings["lows"]:
        prior_low = swings["lows"][-1]["price"]
        if current["low"] < prior_low and current["close"] > prior_low:
            candidates.append({"type": "sell_side_sweep", "level": prior_low})
    if swings["highs"]:
        prior_high = swings["highs"][-1]["price"]
        if current["high"] > prior_high and current["close"] < prior_high:
            candidates.append({"type": "buy_side_sweep", "level": prior_high})
    return candidates or None


def fair_value_gaps(bars):
    """Return three-candle OHLC imbalances; only completed triples are evaluated."""
    if not _valid_bars(bars):
        return []
    gaps = []
    for i in range(2, len(bars)):
        first, third = bars[i-2], bars[i]
        if first["high"] < third["low"]:
            gaps.append({"direction": "bullish", "low": first["high"],
                         "high": third["low"], "index": i})
        elif first["low"] > third["high"]:
            gaps.append({"direction": "bearish", "low": third["high"],
                         "high": first["low"], "index": i})
    return gaps


def momentum_state(bars):
    """Describe the last closed candle's body fraction and direction; no score threshold."""
    if not _valid_bars(bars) or not bars:
        return {"direction": "unknown", "body_fraction": None}
    bar = bars[-1]
    span = bar["high"] - bar["low"]
    if span <= 0:
        return {"direction": "neutral", "body_fraction": 0.0}
    body_fraction = abs(bar["close"] - bar["open"]) / span
    direction = ("bullish" if bar["close"] > bar["open"] else
                 "bearish" if bar["close"] < bar["open"] else "neutral")
    return {"direction": direction, "body_fraction": body_fraction}


def evaluate_context(bars, direction, left=2, right=2):
    """Return independent hybrid evidence for BUY/SELL; never emits a trade signal."""
    if direction not in ("BUY", "SELL"):
        raise ValueError("direction must be BUY or SELL")
    structure = market_structure(bars, left, right)
    sweep = liquidity_sweep(bars, left, right)
    gaps = fair_value_gaps(bars)
    momentum = momentum_state(bars)
    wanted = "bullish" if direction == "BUY" else "bearish"
    sweep_type = "sell_side_sweep" if direction == "BUY" else "buy_side_sweep"
    return {
        "structure": structure["state"],
        "structure_aligned": structure["state"] == wanted,
        "liquidity_sweep": sweep,
        "liquidity_aligned": bool(sweep and any(x["type"] == sweep_type for x in sweep)),
        "latest_fvg": gaps[-1] if gaps else None,
        "fvg_aligned": bool(gaps and gaps[-1]["direction"] == wanted),
        "momentum": momentum,
        "momentum_aligned": momentum["direction"] == wanted,
    }
