"""Chart rendering and OpenAI vision review for visual Supply & Demand criteria.

The model classifies only visual candle geometry. It cannot create trade signals,
set targets, override numeric rules, or fill missing evidence.
"""
import base64
import io
import json
import os
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4.1-mini")
API_URL = "https://api.openai.com/v1/responses"

DEPARTURE_LABELS = {"sideways", "diagonal", "sharp", "uncertain"}
APPROACH_LABELS = {"fast", "diagonal", "sideways", "uncertain"}


def render_candidate_chart(bars, zone, width=1400, height=850):
    """Render origin/departure and latest approach in one two-panel PNG."""
    times = [bar["time"] for bar in bars]
    try:
        origin = times.index(zone["created"])
    except ValueError:
        raise ValueError("zone origin candle is not present in chart data")

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), dpi=100)
    panels = [
        (axes[0], bars[max(0, origin - 5):min(len(bars), origin + 13)],
         "Zone origin and departure"),
        (axes[1], bars[max(0, len(bars) - 35):], "Latest price approach"),
    ]
    for ax, subset, title in panels:
        offset = max(0, len(bars) - 35) if title.startswith("Latest") else max(0, origin - 5)
        for i, candle in enumerate(subset):
            up = candle["close"] >= candle["open"]
            body_low = min(candle["open"], candle["close"])
            body_height = max(abs(candle["close"] - candle["open"]), 1e-8)
            ax.vlines(i, candle["low"], candle["high"], linewidth=1)
            ax.add_patch(Rectangle((i - 0.28, body_low), 0.56, body_height,
                                   fill=up, alpha=0.65, linewidth=0.8))
        ax.axhspan(zone["low"], zone["high"], alpha=0.18)
        ax.set_title(title)
        ax.set_ylabel("XAU/USD")
        ax.grid(True, alpha=0.2)
        ax.set_xlim(-1, max(2, len(subset)))
    fig.suptitle(
        f'{zone["tf"]} {zone["direction"]} | zone {zone["low"]:.2f}-{zone["high"]:.2f}',
        fontsize=13,
    )
    fig.tight_layout()
    output = io.BytesIO()
    fig.savefig(output, format="png", bbox_inches="tight")
    plt.close(fig)
    return output.getvalue()


def _extract_output_text(payload):
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks = []
    for item in payload.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                chunks.append(part.get("text", ""))
    return "\n".join(chunks)


def validate_visual_result(result):
    if result.get("departure") not in DEPARTURE_LABELS:
        raise ValueError("invalid departure classification")
    if result.get("approach") not in APPROACH_LABELS:
        raise ValueError("invalid approach classification")
    confidence = result.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be numeric")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(result.get("evidence"), str):
        raise ValueError("evidence must be text")
    return {
        "departure": result["departure"],
        "approach": result["approach"],
        "confidence": float(confidence),
        "evidence": result["evidence"][:500],
    }


def review_chart_with_vision(image_bytes, api_key, model=MODEL):
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "Inspect this two-panel XAU/USD candlestick chart. The upper panel shows "
        "the zone origin and price departure; the lower panel shows the latest "
        "approach toward the marked zone. Classify only what is visually evident. "
        "departure must be sideways, diagonal, sharp, or uncertain. sharp means "
        "a visually steep/near-vertical departure, not merely large volatility. "
        "approach must be fast, diagonal, sideways, or uncertain. fast means a "
        "visually rapid/impulsive arrival. If chart scale, context, or evidence is "
        "insufficient, use uncertain. Do not infer direction, entry, stop, target, "
        "score, or trading advice. Return JSON only with keys departure, approach, "
        "confidence (0..1), evidence."
    )
    body = {
        "model": model,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image",
                 "image_url": "data:image/png;base64," + encoded,
                 "detail": "high"},
            ],
        }],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": 250,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    raw = _extract_output_text(payload)
    if not raw:
        raise RuntimeError("OpenAI vision response contained no output text")
    return validate_visual_result(json.loads(raw))


def assess_candidate(bars, zone, api_key, model=MODEL):
    chart = render_candidate_chart(bars, zone)
    return review_chart_with_vision(chart, api_key, model)
