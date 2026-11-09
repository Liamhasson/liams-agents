"""One live chat with the Editor on Telegram.

The webhook (`api/telegram.py`) saves Liam's messages to the Notion Inbox and
starts this when he texts. His replies and the Editor's are kept there and the
assets are kept in Notion, so the chat can close after a quiet spell and pick up
later with nothing lost. A message is only marked read once it's been dealt with.

    python -m agents.editor.session --job <id>
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from shared import config, usage
from shared.assets import checklist_message, is_complete, load_assets
from shared.claude import Claude, SONNET
from shared.notion import NotionClient
from shared.notion.client import _long_rt, _title, plain_checkbox, plain_date, plain_number, plain_select, plain_text, plain_title
from shared.telegram import Telegram
from . import context as ctxmod
from .act import Env, apply_actions
from .deliver import safe_parts
from .turn import turn

POLL_SECONDS = 3
_START_STATUSES = {"Approved", "Briefed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Inbox:
    """Liam's messages for one job, as the webhook saved them to Notion."""

    def __init__(self, notion, db_id: str, job_id: str):
        self.notion, self.db, self.job = notion, db_id, job_id

    def _unread(self) -> list[dict]:
        rows = self.notion.query_database(self.db, {"and": [
            {"property": "Read", "checkbox": {"equals": False}},
            {"property": "Job", "rich_text": {"equals": self.job}},
        ]})
        return sorted(rows, key=lambda r: plain_number(r, "Telegram update id") or 0)

    def text(self, row: dict) -> str:
        return plain_text(row, "Full text") or plain_title(row)

    def mark_read(self, row: dict) -> None:
        self.notion.update_page(row["id"], {"Read": {"checkbox": True}})

    def wait(self, seconds: float) -> list[dict]:
        """Unread messages as soon as there are any, or [] after `seconds`."""
        end = time.monotonic() + seconds
        while True:
            rows = self._unread()
            if rows or time.monotonic() >= end:
                return rows
            time.sleep(POLL_SECONDS)


def _open_inbox(notion, ids: dict, job_id: str) -> Inbox:
    return Inbox(notion, ids["Inbox"], job_id)


def _when(row: dict) -> datetime:
    return datetime.fromisoformat(plain_date(row, "Received at").replace("Z", "+00:00"))


def restore_history(notion, inbox_db: str, job_id: str) -> list[dict]:
    """The conversation so far. Unread messages are left out because they're still to be answered."""
    rows = [r for r in notion.query_database(inbox_db, {"property": "Job", "rich_text": {"equals": job_id}})
            if plain_checkbox(r, "Read")]
    return [{"role": "assistant" if plain_select(r, "Direction") == "out" else "user",
             "content": plain_text(r, "Full text") or plain_title(r)}
            for r in sorted(rows, key=_when)]


def log_out(notion, inbox_db: str, job_id: str, text: str) -> None:
    notion.create_page(inbox_db, {
        "Text": _title(text[:100]),
        "Full text": _long_rt(text),
        "Job": _long_rt(job_id),
        "Received at": {"date": {"start": _now().isoformat()}},
        "Read": {"checkbox": True},
        "Direction": {"select": {"name": "out"}},
    })


def _window(notion, job_id: str, until) -> None:
    """Mark the chat live, so the webhook sends Liam's messages here. A date, so a crashed run expires by itself."""
    value = {"start": until.isoformat(timespec="seconds")} if until else None
    notion.update_page(job_id, {"Session until": {"date": value}})


def _say(env: Env, inbox_db: str, text: str) -> None:
    for part in safe_parts(text):
        env.tg.send_message(env.chat, part)
    log_out(env.notion, inbox_db, env.ctx.job_page_id, text)


def checklist(env: Env) -> tuple[str, list]:
    return checklist_message(env.assets, env.ctx.url, env.ctx.job_page_id.replace("-", ""))


def _answer(env: Env, inbox: Inbox, inbox_db: str, row: dict) -> bool:
    """Deal with one message. Returns True if the application was dropped."""
    # Reloaded because a Skip button can change an asset while the chat is open.
    env.assets[:] = load_assets(env.notion, env.ids["Assets"], env.ctx.job_page_id)
    message = inbox.text(row)
    env.history.append({"role": "user", "content": message})
    was_complete = is_complete(env.assets)
    result = turn(env.claude, env.ctx, env.history, env.assets)
    env.history.append({"role": "assistant", "content": result["reply"]})
    _say(env, inbox_db, result["reply"])
    done = apply_actions(env, result["actions"], message)
    for line in done.lines:
        _say(env, inbox_db, line)
    inbox.mark_read(row)
    if done.dropped:
        return True
    complete = is_complete(env.assets)
    if complete and not was_complete:
        env.notion.update_page(env.ctx.job_page_id, {"Status": {"select": {"name": "Ready to send"}}})
        text, buttons = checklist(env)
        env.tg.send_message(env.chat, text, buttons)
    elif was_complete and not complete:
        env.notion.update_page(env.ctx.job_page_id, {"Status": {"select": {"name": "Drafting"}}})
    return False


def _close(env: Env) -> dict:
    env.tg.send_message(env.chat, "Closing for now. Text me to carry on, and everything's saved.")
    return {"closed": True}


def _chat(env: Env, inbox: Inbox, inbox_db: str, idle: float, max_seconds: float, rows: list[dict]) -> dict:
    job_id = env.ctx.job_page_id
    started = last = time.monotonic()
    while True:
        for row in rows:
            # Rolled before the work, because a draft can take minutes and a text during it mustn't start a new run.
            _window(env.notion, job_id, _now() + timedelta(seconds=idle))
            if _answer(env, inbox, inbox_db, row):
                return {"dropped": True}
            last = time.monotonic()
        if time.monotonic() - started >= max_seconds:
            return _close(env)
        rows = inbox.wait(max(0.0, min(50.0, idle - (time.monotonic() - last))))
        if not rows and time.monotonic() - last >= idle:
            _window(env.notion, job_id, None)  # cleared first, so a text after this starts a new run
            rows = inbox.wait(0)  # and one last look for anything sent just before
            if not rows:
                return _close(env)


def run(job_id: str, idle_minutes: float = 15.0, max_minutes: float = 80.0) -> dict:
    notion = NotionClient()
    ids = notion.ensure_databases()
    tg = Telegram()
    chat = config.require("TELEGRAM_CHAT_ID")
    claude = Claude(model=SONNET)
    idle = idle_minutes * 60
    try:
        job = notion.get_page(job_id)
        job_id = job["id"]  # the webhook passes it without dashes; other tables key on Notion's own form
        inbox = _open_inbox(notion, ids, job_id)
        rows = inbox.wait(0)
        if not rows:  # the webhook saves a message first, so this run has nothing to do
            return {"nothing": True}
        ctx = ctxmod.build_context(notion, job)
        env = Env(notion=notion, tg=tg, chat=chat, claude=claude, ctx=ctx, ids=ids,
                  assets=load_assets(notion, ids["Assets"], job_id),
                  history=restore_history(notion, ids["Inbox"], job_id))
        if plain_select(job, "Status") in _START_STATUSES:
            notion.update_page(job_id, {"Status": {"select": {"name": "Drafting"}}})
        return _chat(env, inbox, ids["Inbox"], idle, max_minutes * 60, rows)
    except Exception:
        tg.send_message(chat, "⚠️ Something went wrong on my side. Nothing is lost. Text me to carry on and I'll pick it up.")
        raise
    finally:
        _window(notion, job_id, None)
        usage.log_run(notion, claude, "editor")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Live chat with the Editor on one application")
    ap.add_argument("--job", required=True, help="Notion job page id")
    args = ap.parse_args()
    run(args.job)
    sys.exit(0)
