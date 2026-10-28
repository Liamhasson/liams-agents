"""Send pending job alerts to Telegram.

Picks scored, not-yet-sent jobs (Status 'New', Score >= ask threshold), sends a
full alert for strong matches and a short question for borderline ones, then
marks them awaiting Liam and records the Telegram message id.

    python -m agents.messenger.send              # send all pending
    python -m agents.messenger.send --limit 3    # just the top few (demo)
    python -m agents.messenger.send --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from shared import config
from shared.telegram import Telegram
from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_number, plain_select
from .compose import job_card, ask_card

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
_PRIO = {"fresh": 0, "recent": 1, "older": 2}


def run(limit: int | None = None, dry_run: bool = False) -> dict:
    mcfg = yaml.safe_load(_CONFIG.read_text()).get("matcher", {})
    alert = int(mcfg.get("alert_threshold", 60))
    ask = int(mcfg.get("ask_threshold", 40))

    notion = NotionClient()
    jobs_db = notion.ensure_databases()["Jobs"]
    tg = Telegram()
    chat = config.require("TELEGRAM_CHAT_ID")

    pending = notion.query_database(jobs_db, {"and": [
        {"property": "Status", "select": {"equals": "New"}},
        {"property": "Score", "number": {"greater_than_or_equal_to": ask}},
    ]})
    # Fresh first, then highest score — "apply first" ordering.
    pending.sort(key=lambda p: (_PRIO.get(plain_select(p, "Priority"), 1), -(plain_number(p, "Score") or 0)))
    if limit:
        pending = pending[:limit]

    sent_alert = sent_ask = 0
    for page in pending:
        score = plain_number(page, "Score") or 0
        if score >= alert:
            text, buttons = job_card(page)
            new_status = "Waiting for Liam"
            sent_alert += 1
        else:
            text, buttons = ask_card(page)
            new_status = "Asked Liam"
            sent_ask += 1
        if dry_run:
            print(f"  [dry] {score:>3} {new_status:<16} {plain_title(page)[:50]}")
            continue
        res = tg.send_message(chat, text, buttons)
        notion.update_page(page["id"], {
            "Status": {"select": {"name": new_status}},
            "Telegram message id": {"number": res["message_id"]},
        })
        print(f"  sent {score:>3} → {new_status:<16} {plain_title(page)[:50]}")

    print(f"\nMessenger.send → {sent_alert} alert(s), {sent_ask} question(s)"
          + ("  [dry-run]" if dry_run else ""))
    return {"alerts": sent_alert, "asks": sent_ask}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Send pending job alerts to Telegram")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)
