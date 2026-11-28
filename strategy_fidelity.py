"""Literal scoring primitives for the original Supply & Demand PDF."""
from __future__ import annotations
from math import isfinite
from typing import Iterable, Mapping, Sequence

VALID_TIMEFRAMES = ("MN1", "W1", "D1", "H4", "H1", "M15")
TIMEFRAME_ORDER = {tf: index for index, tf in enumerate(VALID_TIMEFRAMES)}


def _finite_number(value: float, name: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def departure_strength_points(visual_classification: str | None) -> int | None:
    mapping = {"sideways": 0, "diagonal": 1, "sharp": 2, "near_vertical": 2}
    if visual_classification in (None, "uncertain"):
        return None
    if visual_classification not in mapping:
        raise ValueError("unknown departure visual classification")
    return mapping[visual_classification]


def approach_points(visual_classification: str | None) -> int | None:
    mapping = {"fast": 1, "diagonal": 0, "sideways": 0}
    if visual_classification in (None, "uncertain"):
        return None
    if visual_classification not in mapping:
        raise ValueError("unknown approach visual classification")
    return mapping[visual_classification]


def reward_risk_points(entry: float, stop: float, target: float, direction: str) -> tuple[float, int]:
    """Use explicit planned entry, beyond-zone stop and prior opposing destination."""
    entry, stop, target = (_finite_number(entry, "entry"), _finite_number(stop, "stop"),
                           _finite_number(target, "target"))
    if direction not in ("DEMAND", "SUPPLY"):
        raise ValueError("direction must be DEMAND or SUPPLY")
    risk = entry - stop if direction == "DEMAND" else stop - entry
    reward = target - entry if direction == "DEMAND" else entry - target
    if risk <= 0 or reward < 0:
        raise ValueError("stop/target are on the wrong side of entry")
    ratio = reward / risk
    return ratio, (2 if ratio >= 3 else (1 if ratio >= 2 else 0))


def hierarchical_mtf_points(aligned_timeframes: Iterable[str]) -> int:
    """3+ successive frames=2; 2 successive frames=1; otherwise 0."""
    aligned = set(aligned_timeframes)
    unknown = aligned.difference(VALID_TIMEFRAMES)
    if unknown:
        raise ValueError(f"unknown timeframe(s): {sorted(unknown)}")
    # The PDF requires a top-down hierarchy, but examples allow skipping a
    # timeframe when no suitable zone exists on it (e.g. MN1 then D1).
    ordered = sorted(aligned, key=TIMEFRAME_ORDER.__getitem__)
    if len(ordered) >= 3:
        return 2
    if len(ordered) == 2:
        return 1
    return 0


def matching_lower_timeframes(parent_tf: str, parent_zone: Mapping,
                              candidates_by_tf: Mapping[str, Sequence[Mapping]]) -> dict:
    """Find same-direction, price-overlapping zones on strictly lower frames.

    No arbitrary price tolerance is introduced: the candidate price intervals
    must overlap. Every timeframe contributes at most once.
    """
    if parent_tf not in TIMEFRAME_ORDER:
        raise ValueError(f"unknown parent timeframe: {parent_tf}")
    low, high = _finite_number(parent_zone["low"], "zone low"), _finite_number(parent_zone["high"], "zone high")
    direction = parent_zone.get("direction")
    if direction not in ("DEMAND", "SUPPLY") or low >= high:
        raise ValueError("invalid parent zone")
    parent_order = TIMEFRAME_ORDER[parent_tf]
    aligned = [parent_tf]
    matched = []
    for tf in VALID_TIMEFRAMES[parent_order + 1:]:
        for candidate in candidates_by_tf.get(tf, ()):
            if candidate.get("direction") != direction:
                continue
            c_low = _finite_number(candidate["low"], "candidate low")
            c_high = _finite_number(candidate["high"], "candidate high")
            if c_low < c_high and max(low, c_low) <= min(high, c_high):
                aligned.append(tf)
                matched.append(tf)
                break
    return {
        "aligned_timeframes": aligned,
        "matched_lower_timeframes": matched,
        "points": hierarchical_mtf_points(aligned),
    }


def _touches(bar: Mapping[str, float], zone_low: float, zone_high: float) -> bool:
    return float(bar["low"]) <= zone_high and float(bar["high"]) >= zone_low


def count_zone_visits(bars: Sequence[Mapping[str, float]], zone_low: float,
                      zone_high: float, departure_end_index: int) -> int:
    """Count distinct returns after departure; contiguous touches are one visit."""
    if zone_low >= zone_high:
        raise ValueError("zone_low must be below zone_high")
    if departure_end_index < -1 or departure_end_index >= len(bars):
        raise ValueError("departure_end_index out of range")
    visits, in_visit = 0, False
    for bar in bars[departure_end_index + 1:]:
        touching = _touches(bar, zone_low, zone_high)
        if touching and not in_visit:
            visits += 1
        in_visit = touching
    return visits


def visit_points(visits: int) -> int:
    """Fresh/unvisited or first return=2; second=1; third+=0."""
    if visits < 0:
        raise ValueError("visits cannot be negative")
    return 2 if visits <= 1 else (1 if visits == 2 else 0)


def duration_points(bars: Sequence[Mapping[str, float]], zone_low: float,
                    zone_high: float) -> tuple[int, int]:
    """Count touching bars on one timeframe: <=4=1, >=5=0."""
    if zone_low >= zone_high:
        raise ValueError("zone_low must be below zone_high")
    count = sum(1 for bar in bars if _touches(bar, zone_low, zone_high))
    return (1 if count <= 4 else 0), count


def duration_points_by_timeframe(d1_bars: Sequence[Mapping[str, float]],
                                 h4_bars: Sequence[Mapping[str, float]],
                                 zone_low: float, zone_high: float) -> dict:
    """Return a score only when D1 and H4 agree; expose both counts."""
    if not d1_bars or not h4_bars:
        return {"score": None, "d1_count": None, "h4_count": None}
    d1_score, d1_count = duration_points(d1_bars, zone_low, zone_high)
    h4_score, h4_count = duration_points(h4_bars, zone_low, zone_high)
    return {"score": d1_score if d1_score == h4_score else None,
            "d1_count": d1_count, "h4_count": h4_count}


def score_six_criteria(*, departure_visual: str | None, approach_visual: str | None,
                       rr_points: int | None, mtf_points: int | None,
                       visits: int | None, duration_points_value: int | None) -> dict:
    """Return a total only when every criterion has a verified value."""
    if rr_points is not None and rr_points not in (0, 1, 2):
        raise ValueError("invalid RR points")
    if mtf_points is not None and mtf_points not in (0, 1, 2):
        raise ValueError("invalid MTF points")
    if duration_points_value is not None and duration_points_value not in (0, 1):
        raise ValueError("invalid duration points")
    parts = {
        "departure": departure_strength_points(departure_visual),
        "rr": rr_points, "mtf": mtf_points,
        "visits": visit_points(visits) if visits is not None else None,
        "duration": duration_points_value,
        "approach": approach_points(approach_visual),
    }
    complete = all(value is not None for value in parts.values())
    return {"criteria": parts, "complete": complete,
            "total": sum(parts.values()) if complete else None}


def decision_for_score(total: int | None) -> str:
    """PDF: 9-10 pending-order candidate; 7-8 monitor; <=6 reject."""
    if total is None:
        return "incomplete"
    if total < 0 or total > 10:
        raise ValueError("total must be between 0 and 10")
    if total >= 9:
        return "pending_candidate"
    if total >= 7:
        return "monitor"
    return "reject"
