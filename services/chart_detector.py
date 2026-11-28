"""Chart-first visual zone extraction with pixel-to-market calibration.

Vision returns normalized image coordinates only. Prices and timestamps are
derived deterministically from Matplotlib's chart transform, never guessed by AI.
"""
import io
import math
from PIL import Image
from services.gemini_http import generate_json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

DIRECTIONS = {"DEMAND", "SUPPLY"}
DEPARTURES = {"sideways", "diagonal", "sharp", "uncertain"}


def render_market_chart(bars, timeframe):
    if len(bars) < 20:
        raise ValueError("At least 20 closed candles are required")
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    width = 0.62
    for i, bar in enumerate(bars):
        up = bar["close"] >= bar["open"]
        bottom = min(bar["open"], bar["close"])
        height = max(abs(bar["close"] - bar["open"]), 1e-8)
        ax.vlines(i, bar["low"], bar["high"], linewidth=0.9)
        ax.add_patch(Rectangle((i-width/2, bottom), width, height,
                               fill=up, alpha=0.75, linewidth=0.65))
    # Show compact candle indices often enough for visual index selection.
    step = max(1, len(bars)//30)
    ticks = list(range(0, len(bars), step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(i) for i in ticks],
                       rotation=90, ha="center", fontsize=7)
    ax.set_ylabel("XAU/USD price")
    ax.set_xlabel("Closed candle index and timestamp")
    ax.set_title(f"XAU/USD {timeframe} — closed candles")
    ax.grid(True, alpha=0.2)
    ax.set_xlim(-1, len(bars))
    fig.tight_layout()
    # Freeze the final layout before recording the exact data<->pixel transform.
    fig.canvas.draw()
    width_px, height_px = fig.canvas.get_width_height()
    axes = ax.get_window_extent()
    calibration = {
        "image_width": width_px, "image_height": height_px,
        "axes_left": float(axes.x0), "axes_right": float(axes.x1),
        "axes_bottom": float(axes.y0), "axes_top": float(axes.y1),
        "xlim": [float(v) for v in ax.get_xlim()],
        "ylim": [float(v) for v in ax.get_ylim()],
    }
    output = io.BytesIO()
    try:
        fig.savefig(output, format="png", dpi=fig.dpi)
    finally:
        plt.close(fig)

    # Give vision only the actual plotting axes, not titles, tick labels or
    # margins. Keep the exact fractional axes transform relative to this crop.
    with Image.open(io.BytesIO(output.getvalue())) as source:
        crop_left = max(0, int(math.floor(axes.x0)))
        crop_right = min(width_px, int(math.ceil(axes.x1)))
        crop_top = max(0, int(math.floor(height_px - axes.y1)))
        crop_bottom = min(height_px, int(math.ceil(height_px - axes.y0)))
        chart = source.crop((crop_left, crop_top, crop_right, crop_bottom))
        cropped = io.BytesIO()
        chart.save(cropped, format="PNG")

    calibration.update({
        "image_width": crop_right - crop_left,
        "image_height": crop_bottom - crop_top,
        # The crop boundaries are rounded outward to whole pixels; treating
        # that sub-pixel fringe as plot area avoids a false out-of-axes rejection.
        "axes_left": 0.0,
        "axes_right": float(crop_right - crop_left),
        "axes_bottom": 0.0,
        "axes_top": float(crop_bottom - crop_top),
    })
    return cropped.getvalue(), calibration


def map_normalized_bbox_to_market(bbox, calibration, bars):
    """Convert normalized top-left-origin image bbox into calibrated prices/times."""
    if (not isinstance(bbox, list) or len(bbox) != 4 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                not math.isfinite(v) for v in bbox)):
        raise ValueError("bbox must contain four finite normalized coordinates")
    x1, y1, x2, y2 = [float(v) for v in bbox]
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("bbox coordinates must be ordered within [0,1]")
    W, H = calibration["image_width"], calibration["image_height"]
    left, right = calibration["axes_left"], calibration["axes_right"]
    bottom, top = calibration["axes_bottom"], calibration["axes_top"]
    px1, px2 = x1*W, x2*W
    py_top, py_bottom = y1*H, y2*H
    # A zone must lie inside the actual plot area, not labels or margins.
    if px1 < left or px2 > right or py_top < H-top or py_bottom > H-bottom:
        raise ValueError("zone bbox extends outside calibrated plotting axes")
    xmin, xmax = calibration["xlim"]
    ymin, ymax = calibration["ylim"]
    data_x1 = xmin + (px1-left)/(right-left)*(xmax-xmin)
    data_x2 = xmin + (px2-left)/(right-left)*(xmax-xmin)
    # Image y grows downward; market price grows upward.
    data_y_high = ymin + ((H-py_top)-bottom)/(top-bottom)*(ymax-ymin)
    data_y_low = ymin + ((H-py_bottom)-bottom)/(top-bottom)*(ymax-ymin)
    i1 = max(0, min(len(bars)-1, int(round(data_x1))))
    i2 = max(0, min(len(bars)-1, int(round(data_x2))))
    if i1 > i2:
        i1, i2 = i2, i1
    low, high = sorted((data_y_low, data_y_high))
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError("mapped market zone is invalid")
    return {
        "low": float(low), "high": float(high),
        "origin_start": bars[i1]["time"], "origin_end": bars[i2]["time"],
        "origin_start_index": i1, "origin_end_index": i2,
    }


def validate_zone_result(payload, bars, calibration=None):
    """Accept only a visually identified final pre-impulse candle.

    The model selects a candle index and impulse direction. Zone prices are
    taken mechanically from that candle's full wick range (low/high).
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("zones"), list):
        raise ValueError("Vision output must contain a zones array")
    accepted = []
    for item in payload["zones"]:
        if not isinstance(item, dict):
            raise ValueError("Each zone must be an object")
        direction, departure = item.get("direction"), item.get("departure")
        index = item.get("origin_candle_index")
        if direction not in DIRECTIONS or departure not in DEPARTURES:
            raise ValueError("Invalid direction or departure label")
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError("origin_candle_index must be an integer")
        if not 0 <= index < len(bars):
            raise ValueError("origin_candle_index is outside supplied candles")
        if departure != "sharp":
            continue
        candle = bars[index]
        low, high = float(candle["low"]), float(candle["high"])
        if not (math.isfinite(low) and math.isfinite(high) and low < high):
            raise ValueError("Origin candle has invalid OHLC boundaries")
        confidence = item.get("confidence")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("Invalid model confidence")
        evidence = item.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("Visual evidence is required")
        accepted.append({
            "direction": direction, "low": low, "high": high,
            "origin_start": candle["time"], "origin_end": candle["time"],
            "origin_start_index": index, "origin_end_index": index,
            "origin_candle_index": index, "departure": "sharp",
            "confidence": float(confidence), "evidence": evidence[:500],
            "boundary_status": "clear",
            "boundary_method": "origin_candle_full_wick_low_high",
        })
    return accepted

def detect_visual_zones(bars, timeframe, api_key, model="gemini-3.5-flash-lite"):
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    png, calibration = render_market_chart(bars, timeframe)
    prompt = (
        "Act only as a visual annotator for the user's original Supply & Demand "
        "method. Find only a clearly visible SHARP, strong, near-vertical upward "
        "or downward impulse. Identify the LAST SINGLE CANDLE immediately before "
        "that impulse begins, not a multi-candle base and not a candle inside the "
        "impulse. Return origin_candle_index as the integer candle index shown "
        "on the chart x-axis. Demand means the final candle before a sharp upward "
        "impulse from a low; supply means the final candle before a sharp downward "
        "impulse from a high. X-axis ticks are labelled 'index | timestamp'; count "
        "candle positions between labelled ticks to locate the exact candle. "
        "Return departure='sharp' only for the visually steep/near-vertical move "
        "described in the PDF. Do not return bbox, prices, timestamps, or zone "
        "thickness. Software sets zone low/high exactly to that candle's wick "
        "low/high. Never include neighboring candles. Do not use ATR, OHLC "
        "thresholds, or generic patterns to decide if the impulse is sharp. If "
        "origin candle or impulse direction is ambiguous, return no zone. No "
        "score, entry, stop, target, forecast, or recommendation. Empty array "
        "when no defensible sharp impulse exists.\\n\\n"
        "GOVERNING PDF STRATEGY REFERENCE:\\n" + _load_reference()
    )
    schema = {
        "type": "object", "properties": {"zones": {"type": "array", "items": {
            "type": "object", "properties": {
                "direction": {"type": "string", "enum": ["DEMAND", "SUPPLY"]},
                "origin_candle_index": {"type": "integer", "minimum": 0},
                "departure": {"type": "string", "enum": ["sharp"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence": {"type": "string"}
            }, "required": ["direction", "origin_candle_index", "departure",
                            "confidence", "evidence"], "additionalProperties": False
        }}}, "required": ["zones"], "additionalProperties": False
    }
    payload = generate_json(
        prompt, png, schema, api_key, model, timeout=60
    )
    return validate_zone_result(payload, bars, calibration)

def _load_reference():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "STRATEGY_REFERENCE.md"
    if not path.is_file():
        raise RuntimeError("STRATEGY_REFERENCE.md is missing")
    text = path.read_text(encoding="utf-8")
    if len(text) < 1000:
        raise RuntimeError("Strategy reference is incomplete")
    return text
