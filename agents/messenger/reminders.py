"""Daily reminders + expiry.

- Expiry: jobs the Hunter hasn't seen for `expiry_days` are marked Expired and
  stop being reminded (the posting is gone).
- Reminder: one message listing everything still awaiting Liam, oldest first.

    python -m agents.messenger.reminders
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from shared import config
from shared.telegram import Telegram
from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_text, plain_select, plain_date

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def _cfg() -> dict:
    return yaml.safe_load(_CONFIG.read_text()).get("messenger", {})


def _days_since(iso: str, now: datetime) -> float:
    if not iso:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() / 86400
    except Exception:
        return 0.0


def run(dry_run: bool = False) -> dict:
    cfg = _cfg()
    expiry_days = float(cfg.get("expiry_days", 3))
    awaiting = cfg.get("awaiting_statuses", ["Waiting for Liam", "Asked Liam"])

    notion = NotionClient()
    jobs_db = notion.ensure_databases()["Jobs"]
    tg = Telegram()
    chat = config.require("TELEGRAM_CHAT_ID")
    now = datetime.now(timezone.utc)

    rows = notion.query_database(jobs_db, {"or": [
        {"property": "Status", "select": {"equals": s}} for s in awaiting
    ]})

    expired, live = [], []
    for p in rows:
        last_seen = plain_date(p, "Last seen at")
        if last_seen and _days_since(last_seen, now) > expiry_days:
            expired.append(p)
        else:
            live.append(p)

    # Expire vanished postings.
    for p in expired:
        if not dry_run:
            notion.update_page(p["id"], {"Status": {"select": {"name": "Expired"}}})
    if expired:
        print(f"Expired {len(expired)} vanished posting(s).")

    # Remind on everything still live, oldest first.
    live.sort(key=lambda p: plain_date(p, "First seen at"))
    if not live:
        print("Nothing awaiting Liam — no reminder sent.")
        return {"reminded": 0, "expired": len(expired)}

    lines = [f"⏰ <b>{len(live)} job(s) still waiting on you</b> (oldest first):", ""]
    for p in live:
        score = p["properties"].get("Score", {}).get("number")
        lines.append(f"• {plain_title(p)[:48]} @ {plain_text(p,'Company')[:22]}"
                     + (f" ({score}/100)" if score is not None else ""))
    lines.append("\nOpen Notion to Apply/Skip, or reply to each job's message.")
    text = "\n".join(lines)

    if dry_run:
        print(text)
    else:
        tg.send_message(chat, text)
        for p in live:
            cur = p["properties"].get("Reminder count", {}).get("number") or 0
            notion.update_page(p["id"], {
                "Last reminder at": {"date": {"start": now.isoformat()}},
                "Reminder count": {"number": cur + 1},
            })
    print(f"Reminded on {len(live)} job(s); expired {len(expired)}.")
    return {"reminded": len(live), "expired": len(expired)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    run(dry_run=ap.parse_args().dry_run)
