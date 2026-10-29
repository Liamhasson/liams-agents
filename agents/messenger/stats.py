"""Weekly stats to Telegram: what the agents did this week.

    python -m agents.messenger.stats
"""

from __future__ import annotations

from datetime import datetime, timezone

from shared import config, usage
from shared.telegram import Telegram
from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_select, plain_number, plain_date


def _days_since(iso: str, now: datetime) -> float:
    if not iso:
        return 1e9
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() / 86400
    except Exception:
        return 1e9


def run(dry_run: bool = False) -> dict:
    notion = NotionClient()
    ids = notion.ensure_databases()
    tg = Telegram()
    chat = config.require("TELEGRAM_CHAT_ID")
    now = datetime.now(timezone.utc)

    jobs = notion.query_database(ids["Jobs"])
    by_status: dict[str, int] = {}
    new_this_week = 0
    for p in jobs:
        by_status[plain_select(p, "Status") or "—"] = by_status.get(plain_select(p, "Status") or "—", 0) + 1
        if _days_since(plain_date(p, "First seen at"), now) <= 7:
            new_this_week += 1

    # Top sources by jobs found.
    srcs = notion.query_database(ids["Sources"])
    top = sorted(((plain_title(s), plain_number(s, "Jobs found") or 0) for s in srcs),
                 key=lambda x: -x[1])[:5]

    lines = [
        "📊 <b>Weekly stats — Liam's agents</b>", "",
        f"Jobs in system: <b>{len(jobs)}</b>  (+{new_this_week} this week)",
        f"Approved: {by_status.get('Approved', 0)} · "
        f"Applied: {by_status.get('Applied', 0)} · "
        f"Awaiting you: {by_status.get('Waiting for Liam', 0) + by_status.get('Asked Liam', 0)} · "
        f"Skipped: {by_status.get('Skipped', 0)} · "
        f"Expired: {by_status.get('Expired', 0)}",
        "", "<b>Top sources</b> (jobs found):",
    ]
    lines += [f"• {name} — {n}" for name, n in top if n]

    total, per_agent = usage.month_total(notion, now)
    lines += ["", f"<b>Claude usage this month</b> (API-equivalent, paid by your subscription): "
                  f"${total:.2f} of ${usage.limit_usd():.0f}"]
    lines += [f"• {agent} — ${spent:.2f}" for agent, spent in sorted(per_agent.items(), key=lambda x: -x[1])]
    text = "\n".join(lines)

    if dry_run:
        print(text)
    else:
        tg.send_message(chat, text)
    print("Weekly stats sent.")
    return {"jobs": len(jobs), "new_this_week": new_this_week}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    run(dry_run=ap.parse_args().dry_run)
