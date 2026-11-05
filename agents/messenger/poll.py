"""Backup reader for Liam's Telegram taps and replies (manual run only).

Normally Telegram delivers every update instantly to the webhook
(`api/telegram.py`). Telegram allows only one receiver, so while a webhook is
set this poller does nothing. If the webhook is switched off
(`scripts/set_telegram_webhook.py --off`), this reads waiting updates and
answers them with the same logic as the webhook.

    python -m agents.messenger.poll
"""

from __future__ import annotations

from shared import config
from shared.telegram import Telegram
from shared.notion import NotionClient
from .handle import handle_update


def run() -> dict:
    tg = Telegram()
    if tg.webhook_url():
        print("Webhook is active — Telegram delivers updates there. Nothing to poll.")
        return {"handled": 0, "webhook": True}

    notion = NotionClient()
    ids = notion.ensure_databases()
    chat = config.require("TELEGRAM_CHAT_ID")

    updates = tg.get_updates()
    if not updates:
        print("No new updates.")
        return {"handled": 0}

    handled = 0
    for upd in updates:
        try:
            label = handle_update(upd, tg, notion, ids, chat)
            print(f"  update {upd['update_id']}: {label}")
            handled += label not in ("ignored", "not-mine")
        except Exception as e:
            print(f"  ! error on update {upd['update_id']}: {e}")

    tg.get_updates(offset=updates[-1]["update_id"] + 1)  # confirm/clear processed updates
    print(f"Messenger.poll → handled {handled} update(s).")
    return {"handled": handled}


if __name__ == "__main__":
    run()
