"""Faithful, testable calculations for the original Supply/Demand scoring rules.

These functions operate on closed OHLC bars. Visual criteria are explicitly
labelled proxies and must not be represented as exact visual measurements.
"""

TIMEFRAME_ORDER = ("MN1", "W1", "D1", "H4", "H1", "M15")


def bar_touches_zone(bar, zone):
    return bar["low"] <= zone["high"] and bar["high"] >= zone["low"]


def zone_duration_points(bars, zone, departure_end_index):
    """Count post-departure candles that touch the zone (not base candles)."""
    touched = sum(
        1 for bar in bars[departure_end_index + 1:]
        if bar_touches_zone(bar, zone)
    )
    return (1 if touched <= 4 else 0), touched


def count_zone_visits(bars, zone, departure_end_index):
    """Count distinct touch episodes; consecutive candles form one visit."""
    visits = 0
    was_inside = False
    for bar in bars[departure_end_index + 1:]:
        inside = bar_touches_zone(bar, zone)
        if inside and not was_inside:
            visits += 1
        was_inside = inside
    return visits


def visit_points(visits):
    return 2 if visits == 0 else (1 if visits == 1 else 0)


def hierarchical_mtf_matches(zone, zones):
    """Return distinct, overlapping same-direction timeframes in hierarchy order."""
    own_index = TIMEFRAME_ORDER.index(zone["tf"])
    matches = set()
    for other in zones:
        if other is zone or other["direction"] != zone["direction"]:
            continue
        if other["tf"] not in TIMEFRAME_ORDER:
            continue
        other_index = TIMEFRAME_ORDER.index(other["tf"])
        if other_index == own_index:
            continue
        if max(zone["low"], other["low"]) <= min(zone["high"], other["high"]):
            matches.add(other["tf"])
    return sorted(matches, key=TIMEFRAME_ORDER.index)


def mtf_points(matches):
    count = len(set(matches)) + 1
    return 2 if count >= 3 else (1 if count == 2 else 0)


def opposing_zone_target(zone, zones):
    """Nearest opposing zone boundary in the expected profit direction."""
    if zone["direction"] == "DEMAND":
        candidates = [x["low"] for x in zones
                      if x is not zone and x["direction"] == "SUPPLY"
                      and x["low"] > zone["high"]]
        return min(candidates) if candidates else None
    candidates = [x["high"] for x in zones
                  if x is not zone and x["direction"] == "DEMAND"
                  and x["high"] < zone["low"]]
    return max(candidates) if candidates else None


def rr_from_zone(zone, target, stop):
    entry = (zone["low"] + zone["high"]) / 2
    risk = abs(entry - stop)
    if target is None or risk <= 0:
        return 0.0, 0
    reward = target - entry if zone["direction"] == "DEMAND" else entry - target
    rr = reward / risk
    return rr, (2 if rr >= 3 else (1 if rr >= 2 else 0))


def approach_shape_proxy(bars, zone, lookback=5):
    """Conservative OHLC proxy for a clean approach; not a visual-angle measurement."""
    if len(bars) < lookback + 1:
        return False
    sample = bars[-(lookback + 1):-1]
    closes = [b["close"] for b in sample]
    if zone["direction"] == "DEMAND":
        progress = closes[0] - closes[-1]
        retracements = sum(max(0.0, closes[i] - closes[i + 1])
                           for i in range(len(closes) - 1))
        return progress > 0 and retracements <= progress * 0.60
    progress = closes[-1] - closes[0]
    retracements = sum(max(0.0, closes[i + 1] - closes[i])
                       for i in range(len(closes) - 1))
    return progress > 0 and retracements <= progress * 0.60
