"""Chart-first candidate zone extraction using OpenAI vision.

The model reads a calibrated candlestick chart and proposes visual annotations.
This is an observation layer only: it never scores or recommends a trade.
Unclear boundaries are rejected; OHLC/ATR heuristics are not used.
"""
import base64
import io
import json
import math
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

API_URL = "https://api.openai.com/v1/responses"
DIRECTIONS = {"DEMAND", "SUPPLY"}
DEPARTURES = {"sideways", "diagonal", "sharp", "uncertain"}


def render_market_chart(bars, timeframe):
    """Render actual candles with legible calibrated time and price axes."""
    if len(bars) < 20:
        raise ValueError("At least 20 closed candles are required for visual review")
    fig, ax = plt.subplots(figsize=(16, 9), dpi=120)
    width = 0.62
    for i, bar in enumerate(bars):
        up = bar["close"] >= bar["open"]
        bottom = min(bar["open"], bar["close"])
        height = max(abs(bar["close"] - bar["open"]), 1e-8)
        ax.vlines(i, bar["low"], bar["high"], linewidth=0.9)
        ax.add_patch(Rectangle((i-width/2, bottom), width, height,
                               fill=up, alpha=0.75, linewidth=0.65))
    step = max(1, len(bars)//10)
    ticks = list(range(0, len(bars), step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(bars[i]["time"]) for i in ticks],
                       rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("XAU/USD price")
    ax.set_xlabel("Closed candle index and timestamp")
    ax.set_title(f"XAU/USD {timeframe} — full visible history, closed candles")
    ax.grid(True, alpha=0.2)
    ax.set_xlim(-1, len(bars))
    fig.tight_layout()
    output = io.BytesIO()
    try:
        fig.savefig(output, format="png", bbox_inches="tight")
    finally:
        plt.close(fig)
    return output.getvalue()


def validate_zone_result(payload, bars):
    if not isinstance(payload, dict) or not isinstance(payload.get("zones"), list):
        raise ValueError("Vision output must contain a zones array")
    times = {bar["time"] for bar in bars}
    accepted = []
    for item in payload["zones"]:
        if not isinstance(item, dict):
            raise ValueError("Each zone must be an object")
        direction = item.get("direction")
        departure = item.get("departure")
        low, high = item.get("low"), item.get("high")
        start, end = item.get("origin_start"), item.get("origin_end")
        confidence = item.get("confidence")
        if direction not in DIRECTIONS or departure not in DEPARTURES:
            raise ValueError("Invalid direction or departure label")
        if (item.get("boundary_status") != "clear" or
                departure == "uncertain" or
                isinstance(low, bool) or isinstance(high, bool) or
                not isinstance(low, (int, float)) or
                not isinstance(high, (int, float)) or
                not math.isfinite(low) or not math.isfinite(high) or
                low >= high):
            continue
        if low < min(b["low"] for b in bars) or high > max(b["high"] for b in bars):
            continue
        if start not in times or end not in times:
            continue
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("Invalid model confidence")
        if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
            raise ValueError("Visual evidence is required")
        accepted.append({
            "direction": direction, "low": float(low), "high": float(high),
            "origin_start": start, "origin_end": end,
            "departure": departure, "confidence": float(confidence),
            "evidence": item["evidence"][:500],
            "boundary_status": "clear",
        })
    return accepted


def detect_visual_zones(bars, timeframe, api_key, model="gpt-4.1-mini"):
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    image = base64.b64encode(render_market_chart(bars, timeframe)).decode("ascii")
    prompt = (
        "You are a visual annotator, not a trading strategist. Apply only the "
        "attached user's Supply & Demand PDF-derived strategy reference. Inspect "
        "the complete candlestick chart and identify only clearly visible origin "
        "zones from which a sharp/diagonal departure occurs. Demand is a base at "
        "a low followed by upward departure; supply is a base at a high followed "
        "by downward departure. Read price values from the calibrated y-axis and "
        "timestamps from the x-axis. Return the exact lower/upper price boundary "
        "and exact candle timestamps of the origin base. Do not infer boundaries "
        "from ATR, candle-size thresholds, or generic patterns. If exact bounds "
        "or origin timestamps cannot be read, set boundary_status unclear; such "
        "zones will be discarded. Classify departure visually: sideways, diagonal, "
        "sharp, uncertain. Confidence is model confidence only. No score, entry, "
        "stop, target, forecast, or recommendation. Return an empty zones array "
        "if no clearly defensible zone is visible.\n\nSTRATEGY REFERENCE:\n"
        + _load_reference()
    )
    schema = {
        "type": "object",
        "properties": {"zones": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["DEMAND", "SUPPLY"]},
                "low": {"type": "number"}, "high": {"type": "number"},
                "origin_start": {"type": "string"}, "origin_end": {"type": "string"},
                "departure": {"type": "string", "enum": sorted(DEPARTURES)},
                "boundary_status": {"type": "string", "enum": ["clear", "unclear"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence": {"type": "string"}
            },
            "required": ["direction", "low", "high", "origin_start", "origin_end",
                         "departure", "boundary_status", "confidence", "evidence"],
            "additionalProperties": False
        }}},
        "required": ["zones"], "additionalProperties": False
    }
    body = {
        "model": model,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": "data:image/png;base64," + image,
             "detail": "high"}
        ]}],
        "text": {"format": {"type": "json_schema", "name": "visual_zone_annotations",
                            "strict": True, "schema": schema}},
        "max_output_tokens": 1800
    }
    request = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    raw = result.get("output_text")
    if not raw:
        for output in result.get("output", []):
            for part in output.get("content", []):
                if part.get("type") == "output_text":
                    raw = part.get("text", "")
    if not raw:
        raise RuntimeError("OpenAI returned no structured vision output")
    return validate_zone_result(json.loads(raw), bars)


def _load_reference():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "STRATEGY_REFERENCE.md"
    if not path.is_file():
        raise RuntimeError("STRATEGY_REFERENCE.md is missing")
    text = path.read_text(encoding="utf-8")
    if len(text) < 1000:
        raise RuntimeError("Strategy reference is incomplete")
    return text
