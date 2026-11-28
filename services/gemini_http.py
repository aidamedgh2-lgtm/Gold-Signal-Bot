"""Minimal Gemini Developer API client for image-grounded JSON output.

Uses the free-tier compatible generateContent REST endpoint. API keys are sent
in the x-goog-api-key header and are never placed in URLs or log messages.
"""
import json
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models/"


def generate_json(prompt, image_bytes, schema, api_key, model, timeout=60, max_output_tokens=1800):
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("A non-empty image is required")
    if not isinstance(schema, dict):
        raise ValueError("A JSON schema is required")

    import base64
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inlineData": {
                    "mimeType": "image/png",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }},
            ],
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
            "maxOutputTokens": max_output_tokens,
        },
    }
    request = urllib.request.Request(
        API_ROOT + model + ":generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            error = json.loads(detail).get("error", {})
            message = error.get("message") or detail[:400]
            status = error.get("status") or ""
        except (ValueError, AttributeError):
            message, status = detail[:400] or str(exc), ""
        # Never retry quota exhaustion or rate limits automatically: doing so
        # cannot create quota and may consume more of a constrained free tier.
        raise RuntimeError(
            f"Gemini API request failed (HTTP {exc.code}, {status}): {message}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini API network error: {exc.reason}") from exc

    candidates = payload.get("candidates") or []
    if not candidates:
        feedback = payload.get("promptFeedback", {})
        raise RuntimeError(
            "Gemini returned no candidate: " +
            str(feedback.get("blockReason") or "empty response")
        )
    parts = candidates[0].get("content", {}).get("parts", [])
    raw = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not raw.strip():
        raise RuntimeError("Gemini returned no JSON text")
    try:
        result = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("Gemini returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Gemini JSON response must be an object")
    return result
