"""Chart rendering and PDF-grounded OpenAI vision review.

The strategy reference is loaded from the repository on every process start and
included in each vision request. The model supplies visual observations only.
"""
import io
import os
from pathlib import Path
from services.gemini_http import generate_json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle


MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite")
REFERENCE_PATH = Path(__file__).resolve().parents[1] / "STRATEGY_REFERENCE.md"

DEPARTURE_LABELS = {"sideways", "diagonal", "sharp", "uncertain"}
APPROACH_LABELS = {"fast", "diagonal", "sideways", "uncertain"}
READABILITY_LABELS = {"clear", "unclear"}


def load_strategy_reference():
    """Load the committed, PDF-derived reference; fail closed if it is absent."""
    if not REFERENCE_PATH.is_file():
        raise RuntimeError(f"PDF strategy reference is missing: {REFERENCE_PATH}")
    reference = REFERENCE_PATH.read_text(encoding="utf-8").strip()
    if len(reference) < 1000:
        raise RuntimeError("PDF strategy reference is unexpectedly short")
    return reference


def render_candidate_chart(bars, zone):
    """Render the origin/departure and latest approach in two separate panels."""
    times = [bar["time"] for bar in bars]
    try:
        origin = times.index(zone["created"])
    except ValueError as exc:
        raise ValueError("zone origin candle is not present in chart data") from exc

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), dpi=100)
    panels = [
        (axes[0], bars[max(0, origin - 5):min(len(bars), origin + 13)],
         "Origin and departure (candidate zone shaded)"),
        (axes[1], bars[max(0, len(bars) - 35):], "Latest approach to candidate zone"),
    ]
    for ax, subset, title in panels:
        if not subset:
            raise ValueError("insufficient candles for chart panel")
        for i, candle in enumerate(subset):
            up = candle["close"] >= candle["open"]
            body_low = min(candle["open"], candle["close"])
            body_height = max(abs(candle["close"] - candle["open"]), 1e-8)
            ax.vlines(i, candle["low"], candle["high"], linewidth=1)
            ax.add_patch(Rectangle(
                (i - 0.28, body_low), 0.56, body_height,
                fill=up, alpha=0.65, linewidth=0.8,
            ))
        ax.axhspan(zone["low"], zone["high"], alpha=0.18)
        ax.set_title(title)
        ax.set_ylabel("XAU/USD")
        ax.grid(True, alpha=0.2)
        ax.set_xlim(-1, max(2, len(subset)))
    fig.suptitle(
        f'{zone["tf"]} {zone["direction"]} | candidate zone '
        f'{zone["low"]:.2f}-{zone["high"]:.2f}',
        fontsize=13,
    )
    fig.tight_layout()
    output = io.BytesIO()
    try:
        fig.savefig(output, format="png", bbox_inches="tight")
    finally:
        plt.close(fig)
    return output.getvalue()



def validate_visual_result(result):
    if not isinstance(result, dict):
        raise ValueError("vision result must be a JSON object")
    if result.get("departure") not in DEPARTURE_LABELS:
        raise ValueError("invalid departure classification")
    if result.get("approach") not in APPROACH_LABELS:
        raise ValueError("invalid approach classification")
    if result.get("zone_readability") not in READABILITY_LABELS:
        raise ValueError("invalid zone readability classification")
    confidence = result.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be numeric")
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(result.get("evidence"), str):
        raise ValueError("evidence must be text")
    if not isinstance(result.get("unknown_reason"), str):
        raise ValueError("unknown_reason must be text")
    return {
        "departure": result["departure"],
        "approach": result["approach"],
        "zone_readability": result["zone_readability"],
        "confidence": float(confidence),
        "evidence": result["evidence"][:500],
        "unknown_reason": result["unknown_reason"][:300],
    }


def review_chart_with_vision(image_bytes, api_key, model=MODEL):
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    reference = load_strategy_reference()
    instructions = (
        "You are a visual auditor for the user's original Supply & Demand method. "
        "The following PDF-derived reference is the governing rulebook. Follow it "
        "literally; do not import other trading methods.\\n\\n"
        + reference
        + "\\n\\nTASK: inspect the attached XAU/USD chart. The upper panel shows "
        "the candidate zone origin and departure. The lower panel shows the latest "
        "approach. Classify only what is visible. departure: sideways, diagonal, "
        "sharp, uncertain. approach: fast, diagonal, sideways, uncertain. "
        "zone_readability: clear only if the candidate zone boundaries are visually "
        "supported by the chart; otherwise unclear. The shaded band is exactly the full "
        "wick range (low to high) of the single final candle immediately before "
        "the detected sharp impulse; it must not include adjacent candles. Verify "
        "visually that this is truly the last pre-impulse candle and that the "
        "impulse is steep/near-vertical. Reject it as unclear if ambiguous. "
        "Sharp means steep/near-vertical visual shape, "
        "not merely high ATR or a large candle. Fast means a visibly impulsive "
        "return toward the zone. If the chart does not show enough context, use "
        "uncertain/unclear and explain why. Confidence is model confidence only, "
        "not strategy points. Do not output score, direction, entry, stop, target, "
        "pending order, or trading advice."
    )
    schema = {
        "type": "object",
        "properties": {
            "departure": {"type": "string", "enum": sorted(DEPARTURE_LABELS)},
            "approach": {"type": "string", "enum": sorted(APPROACH_LABELS)},
            "zone_readability": {"type": "string", "enum": sorted(READABILITY_LABELS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence": {"type": "string"},
            "unknown_reason": {"type": "string"},
        },
        "required": [
            "departure", "approach", "zone_readability",
            "confidence", "evidence", "unknown_reason",
        ],
        "additionalProperties": False,
    }
    payload = generate_json(
        instructions, image_bytes, schema, api_key, model, timeout=45,
        max_output_tokens=450
    )
    return validate_visual_result(payload)

def assess_candidate(bars, zone, api_key, model=MODEL):
    return review_chart_with_vision(render_candidate_chart(bars, zone), api_key, model)
