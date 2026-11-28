import json
import unittest
from unittest.mock import patch

from services.gemini_http import generate_json


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.payload


class GeminiClientTests(unittest.TestCase):
    def test_sends_image_and_json_schema_using_header_key(self):
        response = {"candidates": [{"content": {"parts": [
            {"text": '{"ok": true}'}
        ]}}]}
        with patch("services.gemini_http.urllib.request.urlopen",
                   return_value=FakeResponse(response)) as mocked:
            result = generate_json(
                "inspect chart", b"png-bytes", {"type": "object"},
                "secret-test-key", "gemini-3.5-flash-lite",
            )
        self.assertEqual(result, {"ok": True})
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_header("X-goog-api-key"), "secret-test-key")
        self.assertNotIn("secret-test-key", request.full_url)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(body["generationConfig"]["responseJsonSchema"], {"type": "object"})
        self.assertEqual(body["contents"][0]["parts"][1]["inlineData"]["mimeType"], "image/png")

    def test_missing_key_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
            generate_json("prompt", b"image", {"type": "object"}, "", "model")

    def test_empty_candidate_fails_closed(self):
        with patch("services.gemini_http.urllib.request.urlopen",
                   return_value=FakeResponse({"candidates": []})):
            with self.assertRaisesRegex(RuntimeError, "no candidate"):
                generate_json("prompt", b"image", {"type": "object"}, "key", "model")

    def test_invalid_json_fails_closed(self):
        response = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
        with patch("services.gemini_http.urllib.request.urlopen",
                   return_value=FakeResponse(response)):
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                generate_json("prompt", b"image", {"type": "object"}, "key", "model")


if __name__ == "__main__":
    unittest.main()
