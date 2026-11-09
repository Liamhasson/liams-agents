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
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import httpx

from shared.assets import LABELS, find, load_assets, set_state
from shared.notion.client import _long_rt, _title, plain_number, plain_select, plain_text, plain_title
from .compose import details_text

# A decision is only valid while the job is still awaiting Liam.
PRE_ACTION = {"New", "Asked Liam", "Waiting for Liam"}
APPLY_WORDS = {"apply", "yes", "y", "go", "✅", "👍"}
SKIP_WORDS = {"skip", "no", "n", "⏭", "👎"}
GREETINGS = {"/start", "start", "hi", "hello", "hey", "/help", "help"}

JOBS_COMMAND = re.compile(r"^/?(?:show |open |my )?jobs(?: (\d{1,3}))?\??$")
JOBS_SHOWN = 8
READY_STATUSES = ("Briefed", "Drafting")
HELP_WORDS = {"/start", "/help", "help"}
BOOT_MINUTES = 5  # the chat counts as live while GitHub starts it up, so a second text doesn't start another
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
        "• Tap <b>Brief me</b>, <b>Skip</b> or <b>Tell me more</b> on a job.\n"
        "• Or reply <b>apply</b>, <b>skip</b> or <b>more</b> to a job message.\n"
        "• Send <b>jobs</b> to see your open matches (or <b>jobs 60</b> for a lower score).\n"
        "• When a brief is waiting, text me normally to start working on it.")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def uuid(jid: str) -> str:
    """Callback data carries the page id without dashes; Notion wants them back."""
    j = jid.replace("-", "")
    if len(j) == 32:
        return f"{j[:8]}-{j[8:12]}-{j[12:16]}-{j[16:20]}-{j[20:]}"
    return jid


def dispatch(workflow: str, job_id: Optional[str] = None) -> Optional[str]:
    """Start a workflow on GitHub. Returns None on success, else what went wrong."""
    token = os.environ.get("GITHUB_DISPATCH_TOKEN")
    if not token:
        return "GITHUB_DISPATCH_TOKEN is not set"
    repo = os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO
    payload: dict = {"ref": "main"}
    if job_id:
        payload["inputs"] = {"job": job_id}
    try:
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
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


def start_director(job_id: Optional[str] = None) -> Optional[str]:
    return dispatch("director.yml", job_id)


def start_editor(job_id: Optional[str] = None) -> Optional[str]:
    return dispatch("editor.yml", job_id)


class Handler:
    """Holds the clients for one update. The two start functions are injectable for tests."""

    def __init__(self, tg, notion, ids: dict, chat, start_director: Callable = start_director,
                 start_editor: Callable = start_editor):
        self.tg, self.notion, self.chat = tg, notion, chat
        self.jobs_db, self.inbox_db = ids["Jobs"], ids.get("Inbox")
        self.start_director, self.start_editor = start_director, start_editor
        self.ids = ids

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
        """Approved jobs with no brief yet, which the Director could pick up."""
        return self.notion.query_database(self.jobs_db, {"and": [
            {"property": "Status", "select": {"equals": "Approved"}},
            {"property": "Director brief", "rich_text": {"is_empty": True}},
        ]})

    def _kick_director(self, page_id: str, title: str) -> str:
        """Start the Director for this job and tell Liam it's coming, or why it isn't."""
        err = self.start_director(page_id.replace("-", ""))
        if err:
            self.tg.send_message(self.chat, f"⚠️ Couldn't start the Director for <b>{html.escape(title)}</b>: "
                                            f"{html.escape(err)}\nThe job is saved as Approved, so nothing is lost.")
            return "director-failed"
        self.tg.send_message(self.chat, "Reading up on them. Your brief comes in a couple of minutes.")
        return "director-started"

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
        return self._kick_director(page["id"], title)

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
        if action in ("resume", "brief"):
            return self._resume(page)
        if action == "start":
            return self._start_button(page, arg)
        if action == "skipasset":
            return self._skip_asset(page, arg)
        if action == "pick":
            return self._pick(page)
        if action == "restore":
            return self._restore(page)
        return "ignored"

    # ---- the Editor --------------------------------------------------------
    def ready_jobs(self) -> list[dict]:
        """Jobs that have a brief and are waiting on Liam to work on them."""
        return self.notion.query_database(self.jobs_db, {"or": [
            {"property": "Status", "select": {"equals": s}} for s in READY_STATUSES]})

    def _start_chat(self, page: dict, text: str, update_id) -> str:
        """Keep the message, mark the chat live, then start the Editor. Its first job is to answer this."""
        title = plain_title(page)
        if text:
            self._to_inbox(text, page["id"], update_id)
        return self._launch(page, title)

    def _launch(self, page: dict, title: str) -> str:
        until = datetime.now(timezone.utc) + timedelta(minutes=BOOT_MINUTES)
        self.notion.update_page(page["id"], {"Session until": {"date": {"start": until.isoformat(timespec="seconds")}}})
        err = self.start_editor(page["id"].replace("-", ""))
        if err:
            self.notion.update_page(page["id"], {"Session until": {"date": None}})
            self.tg.send_message(self.chat, f"⚠️ Couldn't start the Editor for <b>{html.escape(title)}</b>: "
                                            f"{html.escape(err)}\nYour message is saved, so nothing is lost.")
            return "editor-failed"
        self.tg.send_message(self.chat, "Starting the Editor. First reply in about a minute and a half.")
        return "editor-started"

    def _brief_replied_to(self, msg: dict) -> Optional[dict]:
        reply = msg.get("reply_to_message")
        if not reply:
            return None
        rows = self.notion.query_database(self.jobs_db, {
            "property": "Brief message id", "number": {"equals": reply["message_id"]}})
        return rows[0] if rows else None

    def _text_to_editor(self, msg: dict, card: Optional[dict], raw: str, update_id) -> Optional[str]:
        """Start the Editor from a text. None when no job is waiting."""
        replied = self._brief_replied_to(msg) or (card if card and plain_select(card, "Status") in READY_STATUSES else None)
        if replied:
            return self._start_chat(replied, raw, update_id)
        ready = self.ready_jobs()
        if len(ready) == 1:
            return self._start_chat(ready[0], raw, update_id)
        if not ready:
            return None
        self._to_inbox(raw, "", update_id)  # kept until Liam says which job it's for
        buttons = [[(plain_title(p)[:40], f"pick:{p['id'].replace('-', '')}")] for p in ready[:8]]
        self.tg.send_message(self.chat, "Which one is this about?", buttons)
        return "editor-choose"

    def _pick(self, page: dict) -> str:
        waiting = self.notion.query_database(self.inbox_db, {"and": [
            {"property": "Read", "checkbox": {"equals": False}},
            {"property": "Job", "rich_text": {"is_empty": True}},
        ]})
        for row in waiting:
            self.notion.update_page(row["id"], {"Job": _long_rt(page["id"])})
        return self._launch(page, plain_title(page))

    def _start_button(self, page: dict, kind: str) -> str:
        request = f"Start with the {LABELS.get(kind, kind)}."
        live = self.live_session_job()
        if live and live["id"] == page["id"]:
            self._to_inbox(request, page["id"], None)
            return "inbox"
        if live:
            self.tg.send_message(self.chat, "You're in another chat right now. It closes after 15 quiet minutes, "
                                            "then tap this again.")
            return "busy"
        return self._start_chat(page, request, None)

    def _skip_asset(self, page: dict, kind: str) -> str:
        asset = find(load_assets(self.notion, self.ids["Assets"], page["id"]), kind)
        if asset is None:
            return "ignored"
        set_state(self.notion, asset, "skipped")
        self.tg.send_message(self.chat, f"Skipped the {html.escape(LABELS.get(kind, kind))}. The rest of this application stays open.")
        return "asset-skipped"

    def _restore(self, page: dict) -> str:
        title = plain_title(page)
        if plain_select(page, "Status") != "Skipped":
            self.tg.send_message(self.chat, f"<b>{html.escape(title)}</b> isn't dropped.")
            return "already"
        self.notion.update_page(page["id"], {"Status": {"select": {"name": "Briefed"}}})
        self.tg.send_message(self.chat, f"<b>{html.escape(title)}</b> is back. Text me to carry on.")
        return "restored"

    def _resume(self, page: dict) -> str:
        title = plain_title(page)
        if plain_select(page, "Status") != "Approved" or plain_text(page, "Director brief"):
            self.tg.send_message(self.chat, f"<b>{html.escape(title)}</b> has already been briefed.")
            return "already"
        return self._kick_director(page["id"], title)

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
        if text in HELP_WORDS:
            self.tg.send_message(self.chat, "Hi Liam 👋 Matched design jobs arrive here.\n\n" + HELP)
            return "greeting"
        if raw:
            started = self._text_to_editor(msg, card, raw, update_id)
            if started:
                return started
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
            text += "\n\nThese are approved and waiting for a brief:"
            buttons = [[(f"▶️ Brief me: {plain_title(p)[:40]}", f"resume:{p['id'].replace('-', '')}")]
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


def handle_update(update: dict, tg, notion, ids: dict, chat, start_director: Callable = start_director,
                  start_editor: Callable = start_editor) -> str:
    return Handler(tg, notion, ids, chat, start_director, start_editor).handle(update)
