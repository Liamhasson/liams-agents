"""What one application needs: a row in the Notion "Assets" database per asset.

The Director decides which assets a job needs. The Editor drafts them and keeps
their full text here, so a chat can close and pick up again with nothing lost.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, replace
from typing import Optional

from shared.notion.client import (_MAX_ASSET, _long_rt, _rt, _title, plain_number, plain_select, plain_text)

DRAFTED_KINDS = ("cv", "cover_letter", "form_answers", "loom_script")
CHECKLIST_KINDS = ("portfolio", "linkedin", "case_study", "other")
LABELS = {
    "cv": "CV",
    "cover_letter": "Cover letter",
    "form_answers": "Form answers",
    "loom_script": "Loom script",
    "portfolio": "Portfolio link",
    "linkedin": "LinkedIn",
    "case_study": "Case study",
    "other": "Other",
}


@dataclass(frozen=True)
class Planned:
    kind: str
    state: str  # needed or optional
    label: str
    quote: str = ""


@dataclass(frozen=True)
class Asset:
    page_id: str
    job_id: str
    kind: str
    state: str  # needed, optional, drafted, final or skipped
    label: str
    quote: str
    text: str
    first_draft: str
    lines_changed: Optional[int] = None


def _asset(page: dict) -> Asset:
    return Asset(
        page_id=page["id"],
        job_id=plain_text(page, "Job"),
        kind=plain_select(page, "Kind"),
        state=plain_select(page, "State"),
        label=plain_text(page, "Label"),
        quote=plain_text(page, "Quote"),
        text=plain_text(page, "Text"),
        first_draft=plain_text(page, "First draft"),
        lines_changed=plain_number(page, "Lines changed"),
    )


def load_assets(notion, db: str, job_id: str) -> list[Asset]:
    rows = notion.query_database(db, {"property": "Job", "rich_text": {"equals": job_id}})
    return [_asset(r) for r in rows]


def create_assets(notion, db: str, job_id: str, planned: list[Planned]) -> list[Asset]:
    """Add a row for each planned asset. Safe to run twice: existing rows are kept as they are."""
    have = {a.kind: a for a in load_assets(notion, db, job_id)}
    out = []
    for p in planned:
        if p.kind in have:
            out.append(have[p.kind])
            continue
        page = notion.create_page(db, {
            "Name": _title(f"{job_id[:8]} {p.kind}"),
            "Job": _rt(job_id),
            "Kind": {"select": {"name": p.kind}},
            "State": {"select": {"name": p.state}},
            "Label": _rt(p.label),
            "Quote": _rt(p.quote),
        })
        out.append(Asset(page["id"], job_id, p.kind, p.state, p.label, p.quote, "", ""))
    return out


def save_text(notion, asset: Asset, text: str) -> Asset:
    """Store a new version. The first version ever saved stays as the first draft."""
    first = asset.first_draft or text
    props = {
        "Text": _long_rt(text, limit=_MAX_ASSET),
        "State": {"select": {"name": "drafted"}},
    }
    if not asset.first_draft:
        props["First draft"] = _long_rt(text, limit=_MAX_ASSET)
    notion.update_page(asset.page_id, props)
    return replace(asset, text=text, first_draft=first, state="drafted")


def set_state(notion, asset: Asset, state: str) -> Asset:
    notion.update_page(asset.page_id, {"State": {"select": {"name": state}}})
    return replace(asset, state=state)


def checklist_message(assets: list[Asset], url: str, jid: str) -> tuple[str, list]:
    """What's ready, what's skipped, what's Liam's to do, and the link to apply."""
    lines = ["✅ <b>Before you apply</b>", ""]
    for a in assets:
        mark = {"final": "Ready", "skipped": "Skipped", "optional": "Optional, not written"}.get(a.state, "Yours to handle")
        lines.append(f"• {html.escape(a.label, quote=False)}: {mark}")
    if url:
        lines += ["", html.escape(url, quote=False)]
    lines += ["", "Read each one once more, then tap Applied when you've sent it."]
    return "\n".join(lines), [[("✅ Applied", f"applied:{jid}")]]


def find(assets: list[Asset], kind: str) -> Optional[Asset]:
    return next((a for a in assets if a.kind == kind), None)


def is_complete(assets: list[Asset]) -> bool:
    """True when nothing is left to write and at least one drafted asset was decided on.

    An optional asset nobody started doesn't hold things up, and checklist items
    (portfolio link, LinkedIn) are Liam's to handle.
    """
    drafted = [a for a in assets if a.kind in DRAFTED_KINDS]
    if any(a.state in ("needed", "drafted") for a in drafted):
        return False
    return any(a.state in ("final", "skipped") for a in drafted)
