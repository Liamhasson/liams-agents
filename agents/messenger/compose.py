"""Compose Telegram messages from Notion job rows."""

from __future__ import annotations

from shared.notion.client import (
    plain_title, plain_text, plain_select, plain_number, plain_url,
)

PRIORITY_EMOJI = {"fresh": "🔥", "recent": "🟢", "older": "·"}
FIELD_EMOJI = {"rock/live music": "🎸", "music": "🎵"}


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def job_id_for_callback(page: dict) -> str:
    return page["id"].replace("-", "")


def job_card(page: dict) -> tuple[str, list]:
    """Full alert for a strong match: text + Apply/Skip/More buttons."""
    jid = job_id_for_callback(page)
    title = _esc(plain_title(page))
    company = _esc(plain_text(page, "Company"))
    loc = _esc(plain_text(page, "Location")) or "location n/a"
    remote = plain_select(page, "Remote")
    score = plain_number(page, "Score")
    source = _esc(plain_text(page, "Source").split(" — ")[0])
    prio = plain_select(page, "Priority")
    ghost = plain_select(page, "Ghost risk")
    fit = _esc(plain_text(page, "Fit summary"))
    why = _esc(plain_text(page, "Why Liam"))
    gaps = _esc(plain_text(page, "Gaps"))
    url = plain_url(page, "URL") or plain_url(page, "Apply URL")

    head = f"{PRIORITY_EMOJI.get(prio, '')} 🆕 <b>{title}</b> at <b>{company}</b>"
    field = plain_select(page, "Field")
    sub = f"{loc}" + (f" · {remote}" if remote else "") + f" · {score}/100 · via {source}"
    if field and field != "other":
        sub += " · " + " ".join(filter(None, [FIELD_EMOJI.get(field), field]))
    lines = [head, sub, ""]
    if ghost in ("medium", "high"):
        lines.append(f"⚠️ <i>possible ghost/evergreen post ({ghost})</i>")
    if fit:
        lines.append(f"<b>What it is:</b> {fit}")
    if why:
        lines.append(f"<b>Why you:</b> {why}")
    if gaps:
        lines.append(f"<b>Gaps:</b> {gaps}")
    if url:
        lines.append(f'\n🔗 <a href="{_esc(url)}">View posting</a>')
    text = "\n".join(lines)

    buttons = [
        [("✅ Apply", f"apply:{jid}"), ("⏭ Skip", f"skip:{jid}")],
        [("ℹ️ Tell me more", f"more:{jid}")],
    ]
    return text, buttons


def ask_card(page: dict) -> tuple[str, list]:
    """Short borderline question to teach the Matcher."""
    jid = job_id_for_callback(page)
    title = _esc(plain_title(page))
    company = _esc(plain_text(page, "Company"))
    score = plain_number(page, "Score")
    text = f"🤔 Borderline ({score}/100): <b>{title}</b> at <b>{company}</b> — relevant to you?"
    buttons = [[("👍 Yes", f"yes:{jid}"), ("👎 No", f"no:{jid}")]]
    return text, buttons


def details_text(page: dict) -> str:
    """Longer detail for 'Tell me more'."""
    title = _esc(plain_title(page))
    desc = _esc(plain_text(page, "Description"))[:1500]
    url = plain_url(page, "URL") or plain_url(page, "Apply URL")
    out = f"<b>{title}</b>\n\n{desc or 'No description captured.'}"
    if url:
        out += f'\n\n🔗 <a href="{_esc(url)}">View posting</a>'
    return out
