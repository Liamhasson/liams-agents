"""Live co-writing session over Telegram.

Picks an approved, researched job and co-writes the application WITH Liam in
near-real-time (long-polling). On "done" it writes drafts to Notion, renders
one-page PDFs and sends them for a final look.

    python -m agents.writer.session              # auto-pick a ready job
    python -m agents.writer.session --job <id>
    python -m agents.writer.session --minutes 25
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from shared import config
from shared.claude import Claude, SONNET
from shared.telegram import Telegram
from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_text
from modules.pdf.generator import generate_cv_pdf, generate_cover_letter_pdf
from . import context as ctxmod
from . import converse
from .mytone import append_rule

DONE_WORDS = {"done", "finalize", "finalise", "finish", "ready", "that's it",
              "looks good", "make the pdf", "make pdf", "ship it"}
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


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


def _finalize(claude, notion, tg, chat, ctx, job_page_id, history) -> None:
    tg.send_message(chat, "Got it — writing the final drafts and making your PDFs… ✍️")
    drafts = converse.finalize(claude, ctx, history)
    for fix in drafts.get("review_log", []):
        print(f"  [review] {fix}")
    notion.update_page(job_page_id, {
        "CV draft": _rt(drafts["cv_markdown"]),
        "Cover letter draft": _rt(drafts["cover_letter_markdown"]),
        "Status": {"select": {"name": "Ready to send"}},
    })
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = ctx.company.replace(" ", "_").replace("/", "-")[:30] or "job"
    cv_pdf = generate_cv_pdf(drafts["cv_markdown"], OUTPUT_DIR / f"{slug}_cv.pdf")
    tg.send_document(chat, str(cv_pdf), caption=f"📄 CV — {ctx.company}")
    if drafts["cover_letter_markdown"].strip():
        cl_pdf = generate_cover_letter_pdf(drafts["cover_letter_markdown"], OUTPUT_DIR / f"{slug}_cover.pdf",
                                           cv_markdown=drafts["cv_markdown"])
        tg.send_document(chat, str(cl_pdf), caption=f"✉️ Cover letter — {ctx.company}")
    tg.send_message(chat, "Here's your pack — have a final look. Reply <b>approve</b> when happy, "
                          "or tell me what to change. (Submitting comes in the next phase.)")


def run(job_id: str | None = None, minutes: float = 25.0) -> dict:
    notion = NotionClient()
    jobs_db = notion.ensure_databases()["Jobs"]
    tg = Telegram()
    chat = config.require("TELEGRAM_CHAT_ID")
    allowed = str(chat)
    claude = Claude(model=SONNET)

    job = _pick_job(notion, jobs_db, job_id)
    if not job:
        print("No approved+researched job ready to draft.")
        return {"drafted": 0}
    ctx = ctxmod.build_context(notion, job)
    notion.update_page(job["id"], {"Status": {"select": {"name": "Drafting"}}})
    print(f"Co-writing: {ctx.title} @ {ctx.company}")

    # Drain old updates so we only react to new replies.
    offset = None
    seed = tg.get_updates()
    if seed:
        offset = seed[-1]["update_id"] + 1

    history: list[dict] = []
    opening = converse.opening(claude, ctx)
    tg.send_message(chat, opening)
    history.append({"role": "assistant", "content": opening})

    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        updates = tg.get_updates(offset=offset, timeout=50)
        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or {}
            if str(msg.get("chat", {}).get("id")) != allowed or not msg.get("text"):
                continue
            text = msg["text"].strip()
            low = text.lower()
            if low.startswith("mytone:"):
                append_rule(notion, text.split(":", 1)[1].strip())
                tg.send_message(chat, "Saved to your voice guide ✅")
                continue
            if low in DONE_WORDS:
                _finalize(claude, notion, tg, chat, ctx, job["id"], history)
                print(f"Finalised. {claude.cost_summary()}")
                return {"drafted": 1}
            history.append({"role": "user", "content": text})
            answer = converse.reply(claude, ctx, history)
            history.append({"role": "assistant", "content": answer})
            tg.send_message(chat, answer)

    tg.send_message(chat, "Pausing for now — your progress is saved. Reply here anytime to keep going.")
    print(f"Session timed out. {claude.cost_summary()}")
    return {"drafted": 0, "timed_out": True}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Live co-writing session on Telegram")
    ap.add_argument("--job", default=None, help="Notion job page id (default: auto-pick)")
    ap.add_argument("--minutes", type=float, default=25.0)
    args = ap.parse_args()
    run(job_id=args.job, minutes=args.minutes)
