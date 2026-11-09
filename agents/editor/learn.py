"""How much Liam changed, and saving what he approved.

When he marks an asset final, the first draft is compared with the final version
line by line. The number of changed lines is the success metric (it should fall
with every application). The approved CV or letter is saved as a new reference
under Notion Private > Writer references.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import date

from shared.notion import NotionClient

@dataclass(frozen=True)
class Change:
    old: str | None  # None: Liam added a new line
    new: str | None  # None: Liam cut the line


def split_units(text: str, kind: str) -> list[str]:
    """Letters compare sentence by sentence, CVs line by line (headings included)."""
    if kind == "CV":
        return [re.sub(r"^\s*[-*•]\s+", "", l).strip() for l in text.splitlines() if l.strip()]
    return [s.strip() for p in re.split(r"\n\s*\n", text)
            for s in re.split(r"(?<=[.!?])\s+", p.strip()) if s.strip()]


def diff(before: str, after: str, kind: str) -> list[Change]:
    """Every line Liam changed, cut or added between the first draft and the approved one."""
    a, b = split_units(before, kind), split_units(after, kind)
    changes: list[Change] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        changes += _pair(a[i1:i2], b[j1:j2])
    return changes


def _similarity(x: str, y: str) -> float:
    return difflib.SequenceMatcher(a=x.lower(), b=y.lower()).ratio()


def _pair(olds: list[str], news: list[str]) -> list[Change]:
    """Match each old line to the new line it most likely became; leftovers are cuts or additions."""
    free = list(news)
    out: list[Change] = []
    for old in olds:
        best = max(free, key=lambda n: _similarity(old, n), default=None)
        if best is not None and _similarity(old, best) >= 0.4:
            free.remove(best)
            out.append(Change(old, best))
        else:
            out.append(Change(old, None))
    return out + [Change(None, n) for n in free]


def _plain(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


# ---- Notion -------------------------------------------------------------

def _para(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]}}


def add_never_again(notion: NotionClient, line: str, why: str, applies_to: str,
                    application: str) -> None:
    db = notion.load_ids().get("Never again")
    if not db:
        raise RuntimeError("Never again list not set up. Run: python scripts/setup_never_again.py")
    notion.create_page(db, {
        "Line": {"title": [{"text": {"content": line[:1900]}}]},
        "Reason": {"rich_text": [{"text": {"content": why[:1900]}}]},
        "Applies to": {"select": {"name": applies_to}},
        "Date": {"date": {"start": date.today().isoformat()}},
        "Application": {"rich_text": [{"text": {"content": application[:1900]}}]},
    })


def save_reference(notion: NotionClient, title: str, kind: str, company: str, role: str,
                   role_type: str, text: str) -> str:
    """Save an approved letter or CV under Private > Writer references."""
    root = notion.load_ids().get("Writer references")
    if not root:
        raise RuntimeError("Writer references page not set up.")
    meta = [_para(f"Type: {kind}"), _para(f"Company: {company}"), _para(f"Role: {role}"),
            _para(f"Role type: {role_type or 'unknown'}"),
            _para(f"Approved: {date.today().isoformat()}"),
            {"object": "block", "type": "divider", "divider": {}}]
    body = ([_para(l) for l in text.splitlines() if l.strip()] if kind == "CV"
            else [_para(p.strip()) for p in re.split(r"\n\s*\n", text) if p.strip()])
    page = notion._request("POST", "/pages", {
        "parent": {"page_id": root},
        "properties": {"title": {"title": [{"text": {"content": title}}]}}})
    blocks = meta + body
    for i in range(0, len(blocks), 100):
        notion._request("PATCH", f"/blocks/{page['id']}/children", {"children": blocks[i:i + 100]})
    return page["id"]
