"""Poll Telegram for Liam's taps and replies, and update Notion.

Server-less: called on a schedule (~every 5 min). Each run reads new updates,
applies the decision to Notion, then confirms the offset so Telegram clears
them. Processing is idempotent (a decision only applies from a pre-decision
status), so a re-run never double-acts.

    python -m agents.messenger.poll
"""

from __future__ import annotations

from shared import config
from shared.telegram import Telegram
from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_select
from .compose import details_text

# A decision is only valid while the job is still awaiting Liam.
PRE_ACTION = {"New", "Asked Liam", "Waiting for Liam"}
APPLY_WORDS = {"apply", "yes", "y", "go", "✅", "👍"}
SKIP_WORDS = {"skip", "no", "n", "⏭", "👎"}


def _trigger_writer() -> None:
    """Kick off the Writer session workflow (only when running in GitHub Actions)."""
    import os
    import httpx
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        return  # local run — no-op
    try:
        httpx.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/writer.yml/dispatches",
            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
            json={"ref": "main"}, timeout=20,
        )
    except Exception:
        pass


def _safe_answer(tg, qid: str, text: str = "") -> None:
    """Ack a tap — best-effort. With ~5-min polling the query often expires;
    that's harmless (the button spinner clears on its own and we send a
    confirmation message instead), so never let it break the flow."""
    try:
        tg.answer_callback(qid, text)
    except Exception:
        pass


def _uuid(jid: str) -> str:
    j = jid.replace("-", "")
    if len(j) == 32:
        return f"{j[:8]}-{j[8:12]}-{j[12:16]}-{j[16:20]}-{j[20:]}"
    return jid


def run() -> dict:
    tg = Telegram()
    notion = NotionClient()
    jobs_db = notion.ensure_databases()["Jobs"]
    allowed = str(config.require("TELEGRAM_CHAT_ID"))
    chat = config.require("TELEGRAM_CHAT_ID")

    updates = tg.get_updates()
    if not updates:
        print("No new updates.")
        return {"handled": 0}

    handled = 0
    max_id = 0
    for upd in updates:
        max_id = max(max_id, upd["update_id"])
        try:
            if "callback_query" in upd:
                handled += _handle_callback(tg, notion, chat, allowed, upd["callback_query"])
            elif "message" in upd:
                handled += _handle_message(tg, notion, jobs_db, chat, allowed, upd["message"])
        except Exception as e:
            print(f"  ! error on update {upd['update_id']}: {e}")

    tg.get_updates(offset=max_id + 1)  # confirm/clear processed updates
    print(f"Messenger.poll → handled {handled} action(s).")
    return {"handled": handled}


def _apply_decision(notion, page_id: str, status_now: str, decision: str) -> bool:
    if status_now not in PRE_ACTION:
        return False
    target = "Approved" if decision == "apply" else "Skipped"
    notion.update_page(page_id, {"Status": {"select": {"name": target}}})
    return True


def _handle_callback(tg, notion, chat, allowed, cq) -> int:
    qid = cq["id"]
    if str(cq.get("message", {}).get("chat", {}).get("id")) != allowed:
        tg.answer_callback(qid, "Not authorised.")
        return 0
    action, _, jid = cq.get("data", "").partition(":")
    if action == "test":
        _safe_answer(tg, qid, "👍 thanks!")
        return 0
    page_id = _uuid(jid)
    page = notion.get_page(page_id)
    status = plain_select(page, "Status")
    title = plain_title(page)
    if action in ("apply", "yes"):
        changed = _apply_decision(notion, page_id, status, "apply")
        _safe_answer(tg, qid, "✅ Approved" if changed else "Already handled")
        if changed:
            tg.send_message(chat, f"✅ Approved: <b>{title}</b>\nResearching the company and starting the write-up…")
            _trigger_writer()
        return 1 if changed else 0
    if action in ("skip", "no"):
        changed = _apply_decision(notion, page_id, status, "skip")
        _safe_answer(tg, qid, "⏭ Skipped" if changed else "Already handled")
        if changed:
            tg.send_message(chat, f"⏭ Skipped: <b>{title}</b>")
        return 1 if changed else 0
    if action == "more":
        _safe_answer(tg, qid)
        tg.send_message(chat, details_text(page))
        return 1
    _safe_answer(tg, qid)
    return 0


def _handle_message(tg, notion, jobs_db, chat, allowed, msg) -> int:
    if str(msg.get("chat", {}).get("id")) != allowed:
        return 0
    text = (msg.get("text") or "").strip().lower()
    reply = msg.get("reply_to_message")
    if reply:
        matches = notion.query_database(jobs_db, {
            "property": "Telegram message id", "number": {"equals": reply["message_id"]}})
        if matches:
            page = matches[0]
            status = plain_select(page, "Status")
            if text in APPLY_WORDS:
                _apply_decision(notion, page["id"], status, "apply")
                tg.send_message(chat, f"✅ Approved: <b>{plain_title(page)}</b>")
            elif text in SKIP_WORDS:
                _apply_decision(notion, page["id"], status, "skip")
                tg.send_message(chat, "⏭ Skipped.")
            elif "more" in text:
                tg.send_message(chat, details_text(page))
            else:
                tg.send_message(chat, "Reply <b>apply</b>, <b>skip</b>, or <b>more</b> — or use the buttons.")
            return 1
    if text in ("/start", "start", "hi", "hello"):
        tg.send_message(chat, "Hi Liam 👋 Matched design jobs will arrive here. Tap <b>Apply</b> / <b>Skip</b> on each.")
        return 1
    return 0


if __name__ == "__main__":
    run()
