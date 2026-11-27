"""Literal scoring primitives for the original Supply & Demand PDF.

Visual criteria are intentionally manual inputs. OHLC/ATR proxies must never be
silently substituted for the PDF's visual classifications.
"""
from __future__ import annotations

from math import isfinite
from typing import Iterable, Mapping, Sequence

VALID_TIMEFRAMES = ("MN1", "W1", "D1", "H4", "H1", "M15")
HIERARCHICAL_TRIPLETS = (
    ("MN1", "W1", "D1"),
    ("W1", "D1", "H4"),
    ("D1", "H4", "H1"),
)


def _finite_number(value: float, name: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def departure_strength_points(visual_classification: str | None) -> int | None:
    """Sideways=0, diagonal=1, sharp/near-vertical=2; None means unreviewed."""
    mapping = {"sideways": 0, "diagonal": 1, "sharp": 2, "near_vertical": 2}
    if visual_classification is None:
        return None
    if visual_classification not in mapping:
        raise ValueError("unknown departure visual classification")
    return mapping[visual_classification]


def approach_points(visual_classification: str | None) -> int | None:
    """Fast/rocket-like=1; diagonal or sideways=0; None means unreviewed."""
    mapping = {"fast": 1, "diagonal": 0, "sideways": 0}
    if visual_classification is None:
        return None
    if visual_classification not in mapping:
        raise ValueError("unknown approach visual classification")
    return mapping[visual_classification]


def reward_risk_points(entry: float, stop: float, target: float, direction: str) -> tuple[float, int]:
    """Score the PDF's 3:1 / 2:1 / 1:1 thresholds using the actual planned levels."""
    entry = _finite_number(entry, "entry")
    stop = _finite_number(stop, "stop")
    target = _finite_number(target, "target")
    if direction not in ("DEMAND", "SUPPLY"):
        raise ValueError("direction must be DEMAND or SUPPLY")
    risk = entry - stop if direction == "DEMAND" else stop - entry
    reward = target - entry if direction == "DEMAND" else entry - target
    if risk <= 0 or reward < 0:
        raise ValueError("stop/target are on the wrong side of entry")
    ratio = reward / risk
    points = 2 if ratio >= 3 else (1 if ratio >= 2 else 0)
    return ratio, points


def hierarchical_mtf_points(aligned_timeframes: Iterable[str]) -> int:
    """Two points only for a PDF-example hierarchical chain of three frames."""
    aligned = set(aligned_timeframes)
    unknown = aligned.difference(VALID_TIMEFRAMES)
    if unknown:
        raise ValueError(f"unknown timeframe(s): {sorted(unknown)}")
    return 2 if any(set(chain).issubset(aligned) for chain in HIERARCHICAL_TRIPLETS) else 0


def _touches(bar: Mapping[str, float], zone_low: float, zone_high: float) -> bool:
    return float(bar["low"]) <= zone_high and float(bar["high"]) >= zone_low


def count_zone_visits(
    bars: Sequence[Mapping[str, float]], zone_low: float, zone_high: float,
    departure_end_index: int,
) -> int:
    """Count distinct returns after departure; contiguous touching bars are one visit."""
    if zone_low >= zone_high:
        raise ValueError("zone_low must be below zone_high")
    if departure_end_index < -1 or departure_end_index >= len(bars):
        raise ValueError("departure_end_index out of range")
    visits = 0
    in_visit = False
    for bar in bars[departure_end_index + 1:]:
        touching = _touches(bar, zone_low, zone_high)
        if touching and not in_visit:
            visits += 1
        in_visit = touching
    return visits


def visit_points(visits: int) -> int:
    if visits < 1:
        raise ValueError("zone has not been revisited; visit score is not applicable")
    return 2 if visits == 1 else (1 if visits == 2 else 0)


def duration_points(bars: Sequence[Mapping[str, float]], zone_low: float, zone_high: float) -> tuple[int, int]:
    """Count bars touching the zone on the supplied D1/H4 series: <=4=1, >=5=0."""
    if zone_low >= zone_high:
        raise ValueError("zone_low must be below zone_high")
    touched = sum(1 for bar in bars if _touches(bar, zone_low, zone_high))
    return (1 if touched <= 4 else 0), touched


def score_six_criteria(
    *, departure_visual: str | None, approach_visual: str | None,
    rr_points: int, mtf_points: int, visits: int, duration_points_value: int,
) -> dict:
    """Return a total only when both visual judgments have been supplied."""
    if rr_points not in (0, 1, 2) or mtf_points not in (0, 2):
        raise ValueError("invalid RR or MTF points")
    if duration_points_value not in (0, 1):
        raise ValueError("invalid duration points")
    move = departure_strength_points(departure_visual)
    approach = approach_points(approach_visual)
    visit = visit_points(visits)
    parts = {
        "departure": move, "rr": rr_points, "mtf": mtf_points,
        "visits": visit, "duration": duration_points_value, "approach": approach,
    }
    complete = all(value is not None for value in parts.values())
    return {"criteria": parts, "complete": complete,
            "total": sum(parts.values()) if complete else None}
