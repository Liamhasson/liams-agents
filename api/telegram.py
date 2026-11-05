"""Telegram webhook (a Vercel function at /api/telegram).

Telegram sends every tap and message here the moment it happens. We check the
request really comes from Telegram (secret header), answer it with the shared
logic in `agents/messenger/handle.py`, and always return 200 so Telegram doesn't
keep re-sending the same update.

Env vars (set in Vercel): NOTION_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
TELEGRAM_WEBHOOK_SECRET, GITHUB_DISPATCH_TOKEN.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def authorised(header_value: str | None) -> bool:
    """True only if Telegram sent the secret we registered with setWebhook."""
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    return bool(secret) and hmac.compare_digest((header_value or "").encode(), secret.encode())


def process(update: dict) -> str:
    """Answer one update. Imports live here so a bad deploy still returns 200."""
    from shared import config
    from shared.notion import NotionClient
    from shared.telegram import Telegram
    from agents.messenger.handle import handle_update

    chat = config.require("TELEGRAM_CHAT_ID")
    return handle_update(update, Telegram(), NotionClient(), NotionClient.load_ids(), chat)


class handler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):  # health check: open the URL in a browser to see it's alive
        self._reply(200, "Liam's agents: Telegram webhook is running.")

    def do_POST(self):
        # Read the body before answering, even when refusing, or the connection resets.
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if not authorised(self.headers.get("X-Telegram-Bot-Api-Secret-Token")):
            self._reply(401, "unauthorised")
            return
        try:
            update = json.loads(body or b"{}")
            label = process(update)
            print(f"update {update.get('update_id')}: {label}")
        except Exception:
            # Log for Vercel, but still 200: a retry loop would only repeat the failure.
            traceback.print_exc()
        self._reply(200, "ok")
