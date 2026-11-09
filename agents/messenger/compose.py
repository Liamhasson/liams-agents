"""Compose Telegram messages from Notion job rows."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from shared.notion.client import (
    plain_date, plain_title, plain_text, plain_select, plain_number, plain_url,
)

PRIORITY_EMOJI = {"fresh": "🔥", "recent": "🟢", "older": "·"}
FIELD_EMOJI = {"rock/live music": "🎸", "music": "🎵"}


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def job_id_for_callback(page: dict) -> str:
    return page["id"].replace("-", "")


_ASK_NAMES = {"cv": "CV", "cover_letter": "Cover letter", "portfolio": "Portfolio", "loom_or_video": "Loom",
              "case_study": "Case study", "form_questions": "Form questions", "linkedin": "LinkedIn", "other": "Other"}
_ASK_STATES = {"required": "required", "optional": "optional", "not_wanted": "not wanted"}


def asks_line(page: dict) -> str:
    """What the post asks applicants to send. '' for jobs scored before the Matcher read this."""
    raw = plain_text(page, "Application asks")
    if not raw:
        return ""
    asks = json.loads(raw)
    if not asks:
        return "<b>They want:</b> the post doesn't say what to send."
    items = ", ".join(f"{_ASK_NAMES.get(a['kind'], a['kind'])} ({_ASK_STATES.get(a['state'], a['state'])})" for a in asks)
    return f"<b>They want:</b> {items}"


def _rating(page: dict) -> str:
    """Claude's fit, or the old combined score for jobs scored before fit was kept."""
    fit = plain_number(page, "Fit score")
    return f"Fit {fit}" if fit is not None else f"Score {plain_number(page, 'Score')}"


def _flags(page: dict) -> list[str]:
    return [o["name"] for o in page.get("properties", {}).get("Flags", {}).get("multi_select", [])]


def _posted_days_ago(page: dict) -> str:
    posted = plain_date(page, "Posted at")
    if not posted:
        return ""
    try:
        when = datetime.fromisoformat(posted.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - when).days
    return f"posted {days} day{'' if days == 1 else 's'} ago"


def job_card(page: dict) -> tuple[str, list]:
    """Full alert for a strong match: text + Brief me/Skip/More buttons."""
    jid = job_id_for_callback(page)
    title = _esc(plain_title(page))
    company = _esc(plain_text(page, "Company"))
    loc = _esc(plain_text(page, "Location")) or "location n/a"
    remote = plain_select(page, "Remote")
    source = _esc(plain_text(page, "Source").split(" — ")[0])
    prio = plain_select(page, "Priority")
    ghost = plain_select(page, "Ghost risk")
    fit = _esc(plain_text(page, "Fit summary"))
    why = _esc(plain_text(page, "Why Liam"))
    gaps = _esc(plain_text(page, "Gaps"))
    url = plain_url(page, "URL") or plain_url(page, "Apply URL")

    head = f"{PRIORITY_EMOJI.get(prio, '')} 🆕 <b>{title}</b> at <b>{company}</b>"
    field = plain_select(page, "Field")
    sub = f"{loc}" + (f" · {remote}" if remote else "") + f" · {_rating(page)} · via {source}"
    if field and field != "other":
        sub += " · " + " ".join(filter(None, [FIELD_EMOJI.get(field), field]))
    age = _posted_days_ago(page)
    if age:
        sub += f" · {age}"
    breakdown = _esc(plain_text(page, "Score breakdown"))
    lines = [head, sub] + ([f"<i>{breakdown}</i>"] if breakdown else []) + [""]
    if ghost in ("medium", "high"):
        lines.append(f"⚠️ <i>possible ghost/evergreen post ({ghost})</i>")
    if "senior" in _flags(page):
        lines.append("<i>Senior title</i>")
    ad_work = _esc(plain_text(page, "Ad work"))
    if ad_work:
        lines.append(f"⚠️ <b>Includes ad work:</b> <i>{ad_work}</i>")
    asks = asks_line(page)
    if asks:
        lines.append(asks)
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
        [("✅ Brief me", f"apply:{jid}"), ("⏭ Skip", f"skip:{jid}")],
        [("ℹ️ Tell me more", f"more:{jid}")],
    ]
    return text, buttons


def ask_card(page: dict) -> tuple[str, list]:
    """Short borderline question to teach the Matcher."""
    jid = job_id_for_callback(page)
    title = _esc(plain_title(page))
    company = _esc(plain_text(page, "Company"))
    breakdown = _esc(plain_text(page, "Score breakdown"))
    text = f"🤔 Borderline ({_rating(page)}): <b>{title}</b> at <b>{company}</b> — relevant to you?"
    if breakdown:
        text += f"\n<i>{breakdown}</i>"
    buttons = [[("👍 Yes, brief me", f"yes:{jid}"), ("👎 No", f"no:{jid}")]]
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
