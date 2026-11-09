"""Answer one Telegram update: a button tap or a typed message.

Shared by the webhook (`api/telegram.py`, instant) and the backup poller
(`agents.messenger.poll`, manual). Every path ends in a reply to Liam, so a tap
or a message never disappears into silence.

Decisions are idempotent: a job only moves to Approved/Skipped from a
pre-decision status, so a repeated tap says "Already handled" instead of
acting twice.
"""

from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from shared.notion.client import _long_rt, _title, plain_number, plain_select, plain_text, plain_title
from .compose import details_text

# A decision is only valid while the job is still awaiting Liam.
PRE_ACTION = {"New", "Asked Liam", "Waiting for Liam"}
APPLY_WORDS = {"apply", "yes", "y", "go", "✅", "👍"}
SKIP_WORDS = {"skip", "no", "n", "⏭", "👎"}
GREETINGS = {"/start", "start", "hi", "hello", "hey", "/help", "help"}

JOBS_COMMAND = re.compile(r"^/?(?:show |open |my )?jobs(?: (\d{1,3}))?\??$")
JOBS_SHOWN = 8
SKIP_REASONS = {"senior": "too senior", "field": "wrong field", "ad": "ad work",
                "location": "location", "other": "other"}

DEFAULT_REPO = "Liamhasson/liams-agents"
_SETTINGS = os.path.join(os.path.dirname(__file__), "..", "..", "config", "settings.yaml")


def _matcher_setting(name: str, default: int) -> int:
    try:
        import yaml
        with open(_SETTINGS) as fh:
            return int((yaml.safe_load(fh).get("matcher") or {}).get(name, default))
    except Exception:
        return default


def alert_threshold() -> int:
    """The Matcher's 'strong match' score (settings > matcher > alert_threshold)."""
    return _matcher_setting("alert_threshold", 70)

HELP = ("Here's what I understand:\n"
        "• Tap <b>Apply</b>, <b>Skip</b> or <b>Tell me more</b> on a job.\n"
        "• Or reply <b>apply</b>, <b>skip</b> or <b>more</b> to a job message.\n"
        "• Send <b>jobs</b> to see your open matches (or <b>jobs 60</b> for a lower score).\n"
        "• While we're writing an application together, just talk to me normally.")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uuid(jid: str) -> str:
    """Callback data carries the page id without dashes; Notion wants them back."""
    j = jid.replace("-", "")
    if len(j) == 32:
        return f"{j[:8]}-{j[8:12]}-{j[12:16]}-{j[16:20]}-{j[20:]}"
    return jid


def start_writer(job_id: Optional[str] = None) -> Optional[str]:
    """Start the Writer workflow on GitHub. Returns None on success, else what went wrong."""
    token = os.environ.get("GITHUB_DISPATCH_TOKEN")
    if not token:
        return "GITHUB_DISPATCH_TOKEN is not set"
    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO
    payload: dict = {"ref": "main"}
    if job_id:
        payload["inputs"] = {"job": job_id}
    try:
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/writer.yml/dispatches",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            json=payload, timeout=20,
        )
    except Exception as e:  # network trouble
        return f"couldn't reach GitHub ({type(e).__name__})"
    if r.status_code == 204:
        return None
    try:
        reason = r.json().get("message", "")
    except Exception:
        reason = r.text[:200]
    return f"GitHub said {r.status_code}: {reason}"


class Handler:
    """Holds the clients for one update. `start` is injectable for tests."""

    def __init__(self, tg, notion, ids: dict, chat, start: Callable = start_writer):
        self.tg, self.notion, self.chat = tg, notion, chat
        self.jobs_db, self.inbox_db = ids["Jobs"], ids.get("Inbox")
        self.start = start

    # ---- entry point ------------------------------------------------------
    def handle(self, update: dict) -> str:
        """Act on one update. Returns a short label of what happened (for logs and tests)."""
        if "callback_query" in update:
            return self._callback(update["callback_query"])
        if "message" in update:
            return self._message(update["message"], update.get("update_id"))
        return "ignored"

    def _mine(self, chat_id) -> bool:
        return str(chat_id) == str(self.chat)

    def _answer(self, qid: str, text: str = "") -> None:
        """Stop the button's loading spinner. Best-effort: never block the real work."""
        try:
            self.tg.answer_callback(qid, text)
        except Exception:
            pass

    # ---- shared lookups ---------------------------------------------------
    def live_session_job(self) -> Optional[dict]:
        """The job a live Writer session is working on, if one is running now."""
        rows = self.notion.query_database(self.jobs_db, {
            "property": "Session until", "date": {"on_or_after": now_iso()}})
        return rows[0] if rows else None

    def waiting_to_write(self) -> list[dict]:
        """Approved jobs with no draft yet, which the Writer could pick up."""
        return self.notion.query_database(self.jobs_db, {"and": [
            {"property": "Status", "select": {"equals": "Approved"}},
            {"property": "CV draft", "rich_text": {"is_empty": True}},
        ]})

    def _kick_writer(self, page_id: str, title: str) -> str:
        """Start the Writer for this job and tell Liam it's coming, or why it isn't."""
        busy = self.live_session_job()
        err = self.start(page_id.replace("-", ""))
        if err:
            self.tg.send_message(self.chat, f"⚠️ Couldn't start the Writer for <b>{html.escape(title)}</b>: "
                                            f"{html.escape(err)}\nThe job is saved as Approved, so nothing is lost.")
            return "writer-failed"
        if busy and busy["id"] != page_id:
            self.tg.send_message(self.chat, "I'll start on it as soon as the current write-up is done.")
        else:
            self.tg.send_message(self.chat, "Starting the write-up now. My first message comes in a few minutes.")
        return "writer-started"

    def _decide(self, page: dict, decision: str) -> bool:
        """Move a job to Approved/Skipped. False if Liam already decided on it."""
        if plain_select(page, "Status") not in PRE_ACTION:
            return False
        target = "Approved" if decision == "apply" else "Skipped"
        self.notion.update_page(page["id"], {"Status": {"select": {"name": target}}})
        return True

    def _approve(self, page: dict) -> str:
        title = plain_title(page)
        if not self._decide(page, "apply"):
            self.tg.send_message(self.chat, f"<b>{html.escape(title)}</b> is already handled "
                                            f"({html.escape(plain_select(page, 'Status') or 'no status')}).")
            return "already"
        self.tg.send_message(self.chat, f"✅ Approved: <b>{html.escape(title)}</b>")
        return self._kick_writer(page["id"], title)

    def _skip(self, page: dict) -> str:
        title = plain_title(page)
        if not self._decide(page, "skip"):
            self.tg.send_message(self.chat, f"<b>{html.escape(title)}</b> is already handled.")
            return "already"
        jid = page["id"].replace("-", "")
        reasons = [[("Too senior", f"why:{jid}:senior"), ("Wrong field", f"why:{jid}:field")],
                   [("Ad work", f"why:{jid}:ad"), ("Location", f"why:{jid}:location"), ("Other", f"why:{jid}:other")]]
        self.tg.send_message(self.chat, f"⏭ Skipped: <b>{html.escape(title)}</b>\nWhy? Optional, it helps tune the grading.",
                             reasons)
        return "skipped"

    # ---- button taps ------------------------------------------------------
    def _callback(self, cq: dict) -> str:
        qid = cq["id"]
        if not self._mine(cq.get("message", {}).get("chat", {}).get("id")):
            self._answer(qid, "Not authorised.")
            return "not-mine"
        action, _, rest = (cq.get("data") or "").partition(":")
        jid, _, arg = rest.partition(":")
        if action == "test":
            self._answer(qid, "👍 thanks!")
            return "test"
        if not jid:
            self._answer(qid)
            return "ignored"
        if action == "why":
            if arg not in SKIP_REASONS:
                self._answer(qid)
                return "ignored"
            self.notion.update_page(uuid(jid), {"Skip reason": {"select": {"name": SKIP_REASONS[arg]}}})
            self._answer(qid, "Saved")
            return "why"
        self._answer(qid)  # stop the spinner first; the reply message follows
        page = self.notion.get_page(uuid(jid))
        if action in ("apply", "yes"):
            return self._approve(page)
        if action in ("skip", "no"):
            return self._skip(page)
        if action == "more":
            self.tg.send_message(self.chat, details_text(page))
            return "more"
        if action == "resume":
            return self._resume(page)
        return "ignored"

    def _resume(self, page: dict) -> str:
        title = plain_title(page)
        if plain_select(page, "Status") != "Approved" or plain_text(page, "CV draft"):
            self.tg.send_message(self.chat, f"<b>{html.escape(title)}</b> isn't waiting to be written any more.")
            return "already"
        return self._kick_writer(page["id"], title)

    # ---- typed messages ---------------------------------------------------
    def _message(self, msg: dict, update_id) -> str:
        if not self._mine(msg.get("chat", {}).get("id")):
            return "not-mine"
        raw = (msg.get("text") or "").strip()
        text = raw.lower()
        jobs_cmd = JOBS_COMMAND.match(text)
        if jobs_cmd:  # answered here, even mid-session: the Writer can't see other jobs
            return self._list_jobs(int(jobs_cmd.group(1)) if jobs_cmd.group(1) else alert_threshold())
        # A reply to a job card is a decision on that job, even mid-session.
        card = self._card_replied_to(msg)
        if card and (text in APPLY_WORDS or text in SKIP_WORDS or text == "more"):
            if text in APPLY_WORDS:
                return self._approve(card)
            if text in SKIP_WORDS:
                return self._skip(card)
            self.tg.send_message(self.chat, details_text(card))
            return "more"
        live = self.live_session_job()
        if live:
            if not raw:
                self.tg.send_message(self.chat, "I can only read text messages for now.")
                return "not-text"
            self._to_inbox(raw, live["id"], update_id)
            return "inbox"
        if card:
            self.tg.send_message(self.chat, "Reply <b>apply</b>, <b>skip</b> or <b>more</b>, or use the buttons.")
            return "reply-help"
        if text in GREETINGS:
            self.tg.send_message(self.chat, "Hi Liam 👋 Matched design jobs arrive here.\n\n" + HELP)
            return "greeting"
        return self._help()

    def _list_jobs(self, min_score: int) -> str:
        """Open matches (still waiting for Liam's decision) at or above `min_score`."""
        rows = self.notion.query_database(self.jobs_db, {"and": [
            {"or": [{"property": "Status", "select": {"equals": s}} for s in sorted(PRE_ACTION)]},
            {"property": "Score", "number": {"greater_than_or_equal_to": min_score}},
        ]})
        floor = _matcher_setting("min_fit", 50)
        rows = [p for p in rows if plain_number(p, "Fit score") is None or plain_number(p, "Fit score") >= floor]
        rows.sort(key=lambda p: plain_number(p, "Score") or 0, reverse=True)
        if not rows:
            self.tg.send_message(self.chat, f"No open jobs scoring {min_score} or more right now. "
                                            f"Try <b>jobs {max(min_score - 20, 0)}</b> for lower scores.")
            return "jobs-none"
        shown = rows[:JOBS_SHOWN]
        lines = [f"<b>{len(rows)} open job{'s' if len(rows) != 1 else ''} scoring {min_score}+</b>"
                 + (f" (top {JOBS_SHOWN})" if len(rows) > JOBS_SHOWN else "") + ":"]
        buttons = []
        for i, p in enumerate(shown, 1):
            company = plain_text(p, "Company")
            fit = plain_number(p, "Fit score")
            rating = f"Fit {fit}" if fit is not None else str(plain_number(p, "Score") or 0)
            lines.append(f"{i}. <b>{rating}</b> · {html.escape(plain_title(p))}"
                         + (f" at {html.escape(company)}" if company else ""))
            jid = p["id"].replace("-", "")
            buttons.append([(f"✅ Brief {i}", f"apply:{jid}"), (f"ℹ️ More {i}", f"more:{jid}")])
        self.tg.send_message(self.chat, "\n".join(lines), buttons)
        return "jobs"

    def _card_replied_to(self, msg: dict) -> Optional[dict]:
        reply = msg.get("reply_to_message")
        if not reply:
            return None
        matches = self.notion.query_database(self.jobs_db, {
            "property": "Telegram message id", "number": {"equals": reply["message_id"]}})
        return matches[0] if matches else None

    def _help(self) -> str:
        waiting = self.waiting_to_write()[:3]
        text = "I didn't catch that, sorry. " + HELP
        buttons = None
        if waiting:
            text += "\n\nThese are approved and waiting to be written:"
            buttons = [[(f"▶️ Write: {plain_title(p)[:40]}", f"resume:{p['id'].replace('-', '')}")]
                       for p in waiting]
        self.tg.send_message(self.chat, text, buttons)
        return "help"

    def _to_inbox(self, text: str, job_id: str, update_id) -> None:
        props = {
            "Text": _title(text[:100]),
            "Full text": _long_rt(text),
            "Job": _long_rt(job_id),
            "Received at": {"date": {"start": now_iso()}},
            "Read": {"checkbox": False},
        }
        if update_id is not None:
            props["Telegram update id"] = {"number": update_id}
        self.notion.create_page(self.inbox_db, props)


def handle_update(update: dict, tg, notion, ids: dict, chat, start: Callable = start_writer) -> str:
    return Handler(tg, notion, ids, chat, start).handle(update)
