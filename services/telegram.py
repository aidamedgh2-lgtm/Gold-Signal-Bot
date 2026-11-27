"""Telegram notification adapter. Uses the existing bot token and chat ID secrets."""
import json
import urllib.parse
import urllib.request


def send_telegram_message(message, bot_token, chat_id):
    if not bot_token or not chat_id:
        raise RuntimeError("Telegram credentials are required to send a message")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError("Telegram rejected message")
