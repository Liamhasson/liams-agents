"""Point Telegram at the webhook on Vercel (or switch it off).

    python scripts/set_telegram_webhook.py --new-secret          # add TELEGRAM_WEBHOOK_SECRET to .env
    python scripts/set_telegram_webhook.py --url https://<project>.vercel.app/api/telegram
    python scripts/set_telegram_webhook.py --status
    python scripts/set_telegram_webhook.py --off                 # back to the backup poller

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET from .env. Never prints them.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared import config  # noqa: E402  (loads .env)
from shared.telegram import Telegram  # noqa: E402

ENV = ROOT / ".env"


def new_secret() -> None:
    text = ENV.read_text() if ENV.exists() else ""
    if any(line.startswith("TELEGRAM_WEBHOOK_SECRET=") and line.strip() != "TELEGRAM_WEBHOOK_SECRET="
           for line in text.splitlines()):
        print("TELEGRAM_WEBHOOK_SECRET is already in .env — keeping it.")
        return
    lines = [l for l in text.splitlines() if not l.startswith("TELEGRAM_WEBHOOK_SECRET=")]
    lines.append(f"TELEGRAM_WEBHOOK_SECRET={secrets.token_urlsafe(32)}")
    ENV.write_text("\n".join(lines) + "\n")
    print("Added TELEGRAM_WEBHOOK_SECRET to .env (copy the same value into Vercel).")


def status(tg: Telegram) -> None:
    info = tg.webhook_info()
    print(f"Webhook URL:     {info.get('url') or '(none, backup poller mode)'}")
    print(f"Waiting updates: {info.get('pending_update_count', 0)}")
    if info.get("last_error_message"):
        print(f"Last error:      {info['last_error_message']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Set up the Telegram webhook")
    ap.add_argument("--url", help="Full webhook URL, ending in /api/telegram")
    ap.add_argument("--off", action="store_true", help="Remove the webhook")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--new-secret", action="store_true")
    a = ap.parse_args()

    if a.new_secret:
        new_secret()
        return
    tg = Telegram()
    if a.off:
        tg.delete_webhook()
        print("Webhook removed. Run the Poll workflow by hand to read taps.")
    elif a.url:
        if not a.url.startswith("https://") or not a.url.rstrip("/").endswith("/api/telegram"):
            sys.exit("The URL must start with https:// and end with /api/telegram")
        tg.set_webhook(a.url.rstrip("/"), config.require("TELEGRAM_WEBHOOK_SECRET"))
        print("Webhook set.")
    status(tg)


if __name__ == "__main__":
    main()
