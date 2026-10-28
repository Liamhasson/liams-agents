"""Minimal Telegram Bot API client.

Telegram has no 24-hour window, no templates and no per-message fees, so this is
much simpler than a WhatsApp integration: send messages with inline buttons, and
read updates (taps + replies) by polling.
"""

from __future__ import annotations

from typing import Optional

import httpx

from . import config


class Telegram:
    def __init__(self, token: Optional[str] = None):
        self.token = token or config.require("TELEGRAM_BOT_TOKEN")
        self.base = f"https://api.telegram.org/bot{self.token}"
        self._http = httpx.Client(timeout=35)

    def _post(self, method: str, payload: dict) -> dict:
        r = self._http.post(f"{self.base}/{method}", json=payload)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} failed: {data}")
        return data["result"]

    def get_me(self) -> dict:
        return self._post("getMe", {})

    def send_message(self, chat_id, text: str, buttons: Optional[list] = None) -> dict:
        """Send a message. `buttons` is a list of rows, each row a list of
        (label, callback_data) tuples -> rendered as inline buttons."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": label, "callback_data": data} for (label, data) in row]
                    for row in buttons
                ]
            }
        return self._post("sendMessage", payload)

    def answer_callback(self, callback_query_id: str, text: str = "") -> dict:
        return self._post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

    def send_document(self, chat_id, file_path: str, caption: str = "") -> dict:
        import os
        with open(file_path, "rb") as fh:
            data = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            r = self._http.post(
                f"{self.base}/sendDocument",
                data=data,
                files={"document": (os.path.basename(file_path), fh, "application/pdf")},
            )
        result = r.json()
        if not result.get("ok"):
            raise RuntimeError(f"Telegram sendDocument failed: {result}")
        return result["result"]

    def get_updates(self, offset: Optional[int] = None, timeout: int = 0) -> list[dict]:
        payload: dict = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        return self._post("getUpdates", payload)
