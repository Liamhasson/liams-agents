"""Live co-writing session over Telegram.

Picks an approved, researched job and co-writes the application WITH Liam in
near-real-time. On "done" it writes drafts to Notion, renders
one-page PDFs and sends them for a final look.

Liam's replies reach the Writer through the Notion Inbox: the Telegram webhook
(`api/telegram.py`) owns the update stream and drops his messages there while
this job's "Session until" is in the future. Liam then asks for changes or
replies "approve". On approve the Writer counts the lines he changed, saves the
approved pack as a reference, and asks once which changed lines go on his
"Never again" list (docs/workplan-writer-learns.md, step 3).

    python -m agents.editor.session              # auto-pick a ready job
    python -m agents.editor.session --job <id>
    python -m agents.editor.session --minutes 25
"""

from __future__ import annotations

import argparse
import html
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared import config, usage
from shared.claude import Claude, SONNET
from shared.telegram import Telegram
from shared.notion import NotionClient
from shared.notion.client import plain_checkbox, plain_number, plain_title, plain_text
from modules.pdf.generator import generate_cv_pdf, generate_cover_letter_pdf
from . import context as ctxmod
from . import converse
from . import learn
from .mytone import append_rule

DONE_WORDS = {"done", "finalize", "finalise", "finish", "ready", "that's it",
              "looks good", "make the pdf", "make pdf", "ship it"}
APPROVE_WORDS = {"approve", "approved", "i approve", "approve it", "looks good", "perfect"}
DROP_WORDS = {"drop", "drop this", "drop it", "drop this job", "drop the job", "cancel",
              "cancel this", "stop this", "stop writing", "not interested", "skip this", "skip this job"}
DROP_STARTS = ("drop this", "drop it", "drop the job", "cancel this", "skip this job")
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"
POLL_SECONDS = 3


def wants_drop(low: str) -> bool:
    """'drop', 'drop this. I don't want crypto', 'cancel this'... but not 'stop using dashes'."""
    low = low.strip().rstrip(".!")
    return low in DROP_WORDS or low.startswith(DROP_STARTS)


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

    def _take(self, rows: list[dict]) -> list[str]:
        texts = []
        for r in rows:
            if plain_checkbox(r, "Read"):
                continue
            self.notion.update_page(r["id"], {"Read": {"checkbox": True}})
            texts.append(plain_text(r, "Full text") or plain_title(r))
        return texts

    def drain(self) -> None:
        """Mark leftovers from an earlier session as read, so we only react to new replies."""
        self._take(self._unread())

    def wait(self, seconds: float) -> list[str]:
        """Return new messages as soon as any arrive, or [] after `seconds`."""
        end = time.monotonic() + seconds
        while True:
            texts = self._take(self._unread())
            if texts or time.monotonic() >= end:
                return texts
            time.sleep(POLL_SECONDS)


def _open_inbox(notion, ids: dict, job_id: str) -> Inbox:
    return Inbox(notion, ids["Inbox"], job_id)


def _session_until(notion, job_page_id: str, until: datetime | None) -> None:
    """Mark the session live (the webhook routes Liam's messages here) or over."""
    value = {"start": until.isoformat(timespec="seconds")} if until else None
    notion.update_page(job_page_id, {"Session until": {"date": value}})


def _offer_next(notion, tg, chat, jobs_db: str, current_id: str) -> None:
    """If more approved jobs are waiting, offer to write the next one."""
    try:
        waiting = [p for p in notion.query_database(jobs_db, {"and": [
            {"property": "Status", "select": {"equals": "Approved"}},
            {"property": "CV draft", "rich_text": {"is_empty": True}},
        ]}) if p["id"] != current_id]
    except Exception:
        return
    if waiting:
        nxt = waiting[0]
        tg.send_message(chat, f"Next approved job waiting: <b>{html.escape(plain_title(nxt))}</b>",
                        [[("▶️ Write it", f"resume:{nxt['id'].replace('-', '')}")]])


def _rt(s: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": (s or "")[:1900]}}]}


def _pick_job(notion: NotionClient, jobs_db: str, job_id: str | None) -> dict | None:
    if job_id:
        return notion.get_page(job_id)
    ready = notion.query_database(jobs_db, {"and": [
        {"property": "Status", "select": {"equals": "Approved"}},
        {"property": "Research notes", "rich_text": {"is_not_empty": True}},
        {"property": "CV draft", "rich_text": {"is_empty": True}},
    ]})
    return ready[0] if ready else None


def _send_pack(tg, chat, ctx, drafts) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = ctx.company.replace(" ", "_").replace("/", "-")[:30] or "job"
    cv_pdf = generate_cv_pdf(drafts["cv_markdown"], OUTPUT_DIR / f"{slug}_cv.pdf")
    tg.send_document(chat, str(cv_pdf), caption=f"📄 CV — {ctx.company}")
    if drafts["cover_letter_markdown"].strip():
        cl_pdf = generate_cover_letter_pdf(drafts["cover_letter_markdown"], OUTPUT_DIR / f"{slug}_cover.pdf",
                                           cv_markdown=drafts["cv_markdown"])
        tg.send_document(chat, str(cl_pdf), caption=f"✉️ Cover letter — {ctx.company}")


def _save_drafts(notion, job_page_id, drafts, extra: dict | None = None) -> None:
    notion.update_page(job_page_id, {
        "CV draft": _rt(drafts["cv_markdown"]),
        "Cover letter draft": _rt(drafts["cover_letter_markdown"]),
        **(extra or {}),
    })


def _finalize(claude, notion, tg, chat, ctx, job_page_id, history) -> dict:
    tg.send_message(chat, "Got it — writing the final drafts and making your PDFs… ✍️")
    drafts = converse.finalize(claude, ctx, history)
    for fix in drafts.get("review_log", []):
        print(f"  [review] {fix}")
    _save_drafts(notion, job_page_id, drafts)
    _send_pack(tg, chat, ctx, drafts)
    reused = drafts.get("reused") or {}
    note = ("\n\nReused word for word from packs you approved: "
            + ", ".join(f"{n} line{'s' if n != 1 else ''} from {html.escape(t)}" for t, n in reused.items())
            + ". Openings and closings are new." if reused else "")
    tg.send_message(chat, "Here's your pack — have a final look. Reply <b>approve</b> when happy, "
                          f"or tell me what to change. (Submitting comes in the next phase.){note}")
    return drafts


def _revise(claude, notion, tg, chat, ctx, job_page_id, drafts, request) -> dict:
    res = converse.revise(claude, ctx, drafts, request)
    drafts = {**drafts, "cv_markdown": res["cv_markdown"],
              "cover_letter_markdown": res["cover_letter_markdown"]}
    _save_drafts(notion, job_page_id, drafts)
    _send_pack(tg, chat, ctx, drafts)
    issues = (converse.voice_issues(ctx, drafts["cv_markdown"], "CV")
              + converse.voice_issues(ctx, drafts["cover_letter_markdown"], "cover letter"))
    heads_up = f"\n\nHeads up, the check found: {', '.join(sorted(set(issues)))}" if issues else ""
    tg.send_message(chat, f"{html.escape(res['note'] + heads_up)}\n\n"
                          "Reply <b>approve</b> or tell me what else to change.")
    return drafts


def _approve(notion, tg, chat, ctx, job_page_id, first, drafts) -> list[tuple[str, learn.Change]]:
    """Count changed lines, save the approved pack as a reference, return never-again candidates."""
    docs = [("CV", "cv", "resume")]
    if drafts["cover_letter_markdown"].strip():
        docs.append(("cover letter", "cover_letter", "cover letter"))
    changed, pending = 0, []
    for kind, key, name in docs:
        changes = learn.diff(first[f"{key}_markdown"], drafts[f"{key}_markdown"], kind)
        changed += len(changes)
        pending += [(kind, c) for c in learn.candidates(changes, ctx.never_again)]
        learn.save_reference(notion, f"{ctx.company} {name}", kind, ctx.company, ctx.title,
                             ctx.role_type, drafts[f"{key}_markdown"])
    _save_drafts(notion, job_page_id, drafts, {"Lines changed": {"number": changed}})
    print(f"Approved. Lines changed from the first draft: {changed}")
    tg.send_message(chat, f"Approved ✅ You changed {changed} line{'s' if changed != 1 else ''} "
                          "from my first draft. I saved this pack as a reference for next time.")
    return pending


def _add_picked(notion, tg, chat, ctx, pending, picks) -> None:
    application = f"{ctx.company}, {ctx.title}"
    for i in picks:
        kind, change = pending[i]
        learn.add_never_again(notion, change.old, learn.reason(change), kind, application)
    tg.send_message(chat, f"Added {len(picks)} line{'s' if len(picks) != 1 else ''} to your Never again list ✅"
                    if picks else "Okay, nothing added.")


def run(job_id: str | None = None, minutes: float = 25.0) -> dict:
    notion = NotionClient()
    ids = notion.ensure_databases()
    jobs_db = ids["Jobs"]
    tg = Telegram()
    chat = config.require("TELEGRAM_CHAT_ID")
    claude = Claude(model=SONNET)

    job = _pick_job(notion, jobs_db, job_id)
    if not job:
        print("No approved+researched job ready to draft.")
        return {"drafted": 0}
    ctx = ctxmod.build_context(notion, job)
    notion.update_page(job["id"], {"Status": {"select": {"name": "Drafting"}}})
    print(f"Co-writing: {ctx.title} @ {ctx.company}")

    inbox = _open_inbox(notion, ids, job["id"])
    inbox.drain()
    _session_until(notion, job["id"], datetime.now(timezone.utc) + timedelta(minutes=minutes))
    try:
        result = _converse(notion, tg, chat, claude, ctx, job, inbox, minutes)
    finally:
        _session_until(notion, job["id"], None)
    _offer_next(notion, tg, chat, jobs_db, job["id"])
    return result


def _converse(notion, tg, chat, claude, ctx, job, inbox, minutes) -> dict:
    history: list[dict] = []
    opening = converse.opening(claude, ctx)
    tg.send_message(chat, opening)
    history.append({"role": "assistant", "content": opening})

    # writing -> review (pack sent, Liam edits or approves) -> confirm (never-again pick)
    phase, first, drafts, pending = "writing", None, None, []
    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        for text in inbox.wait(min(50.0, max(0.0, deadline - time.monotonic()))):
            text = text.strip()
            low = text.lower()
            if low.startswith("mytone:"):
                append_rule(notion, text.split(":", 1)[1].strip())
                tg.send_message(chat, "Saved to your voice guide ✅")
                continue
            if wants_drop(low):
                notion.update_page(job["id"], {"Status": {"select": {"name": "Skipped"}}})
                tg.send_message(chat, f"Dropped ✅ <b>{html.escape(ctx.title)}</b> at {html.escape(ctx.company)} "
                                      "is marked Skipped and this write-up has ended.")
                usage.log_run(notion, claude, "writer")
                return {"drafted": 0, "dropped": True}
            if phase == "writing":
                if low in DONE_WORDS:
                    first = _finalize(claude, notion, tg, chat, ctx, job["id"], history)
                    drafts, phase = first, "review"
                    continue
                history.append({"role": "user", "content": text})
                answer = converse.reply(claude, ctx, history)
                history.append({"role": "assistant", "content": answer})
                tg.send_message(chat, answer)
            elif phase == "review":
                if low.rstrip(".!") in APPROVE_WORDS:
                    pending = _approve(notion, tg, chat, ctx, job["id"], first, drafts)
                    if not pending:
                        return _finish(notion, job["id"], claude, approved=True)
                    tg.send_message(chat, learn.confirm_message(pending))
                    phase = "confirm"
                    continue
                drafts = _revise(claude, notion, tg, chat, ctx, job["id"], drafts, text)
            else:  # confirm
                picks = learn.parse_pick(text, len(pending))
                if picks is None:
                    tg.send_message(chat, "Reply <b>all</b>, <b>none</b>, or the numbers to add (like 1, 3).")
                    continue
                _add_picked(notion, tg, chat, ctx, pending, picks)
                return _finish(notion, job["id"], claude, approved=True)

    tg.send_message(chat, "Pausing for now, your progress is saved." + (
        "" if phase != "writing" else " Send me any message and tap <b>Write</b> to start again."))
    # Drafts exist → Ready to send. No drafts yet → back to Approved, so "Write it" can restart it.
    notion.update_page(job["id"], {"Status": {"select": {"name": "Ready to send" if phase != "writing" else "Approved"}}})
    usage.log_run(notion, claude, "writer")
    print(f"Session timed out in phase '{phase}'. {claude.cost_summary()}")
    return {"drafted": int(phase != "writing"), "timed_out": True}


def _finish(notion, job_page_id, claude, approved: bool) -> dict:
    notion.update_page(job_page_id, {"Status": {"select": {"name": "Ready to send"}}})
    usage.log_run(notion, claude, "writer")
    print(f"Finalised. {claude.cost_summary()}")
    return {"drafted": 1, "approved": approved}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Live co-writing session on Telegram")
    ap.add_argument("--job", default=None, help="Notion job page id (default: auto-pick)")
    ap.add_argument("--minutes", type=float, default=25.0)
    args = ap.parse_args()
    run(job_id=args.job, minutes=args.minutes)
