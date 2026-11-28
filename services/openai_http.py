"""Bounded retry handling for transient OpenAI API rate limits."""
import json
import time
import urllib.error
import urllib.request


def openai_urlopen(request, timeout=60, max_attempts=5):
    """Retry transient 429/5xx responses; fail immediately on exhausted quota."""
    for attempt in range(max_attempts):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body).get("error", {})
            except (ValueError, AttributeError):
                detail = {}
            code = detail.get("code") or detail.get("type") or ""
            message = detail.get("message") or body[:500] or str(exc)
            if exc.code == 429 and code == "insufficient_quota":
                raise RuntimeError(
                    f"OpenAI quota exhausted (HTTP 429): {message}"
                ) from exc
            retryable = exc.code == 429 or exc.code in {500, 502, 503, 504}
            if not retryable or attempt == max_attempts - 1:
                raise RuntimeError(
                    f"OpenAI API request failed (HTTP {exc.code}): {message}"
                ) from exc
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2 ** (attempt + 1)
            except (TypeError, ValueError):
                delay = 2 ** (attempt + 1)
            time.sleep(min(max(delay, 1), 30))
