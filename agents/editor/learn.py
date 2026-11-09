"""The Writer learns from Liam's edits (docs/workplan-writer-learns.md, step 3).

When Liam approves a pack, the first draft is compared with the approved version
line by line. The number of changed lines is the success metric (it should fall
with every application). Lines he replaced or cut become candidates for the
"Never again" list, and are only added after he confirms them. The approved
version is saved as a new reference under Notion Private > Writer references.
"""

from __future__ import annotations

import difflib
import html
import re
from dataclasses import dataclass
from datetime import date

from shared.notion import NotionClient
from .context import NeverAgain

ALL_WORDS = {"all", "yes", "yes all", "add all", "all of them"}
NONE_WORDS = {"none", "no", "nope", "skip", "no thanks", "neither"}


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


def candidates(changes: list[Change], known: list[NeverAgain]) -> list[Change]:
    """Replaced or cut lines that aren't on the list yet (one entry per line).

    A line Liam only added words to ("Nobody asked" -> "At Cyvore nobody asked")
    still counts as a change, but it isn't a line he rejected, so it's not offered.
    """
    have = {e.line.strip().lower() for e in known}
    out: list[Change] = []
    for c in changes:
        if c.old and c.new and _plain(c.old) in _plain(c.new):
            continue
        if c.old and c.old.strip().lower() not in have:
            have.add(c.old.strip().lower())
            out.append(c)
    return out


def reason(change: Change) -> str:
    """Liam's own fix is the reason. Never guess why he changed it."""
    return f'Liam rewrote it as: "{change.new}"' if change.new else "Liam cut it."


def parse_pick(text: str, n: int) -> list[int] | None:
    """'all' / 'none' / '1, 3' -> 0-based indexes. None if the reply isn't a pick."""
    low = text.strip().lower().rstrip(".!")
    if low in ALL_WORDS:
        return list(range(n))
    if low in NONE_WORDS:
        return []
    if not re.fullmatch(r"[\d\s,and&]+", low):
        return None
    picks = sorted({int(x) - 1 for x in re.findall(r"\d+", low)})
    if not picks or any(p < 0 or p >= n for p in picks):
        return None
    return picks


def confirm_message(items: list[tuple[str, Change]]) -> str:
    many = len(items) != 1
    lines = [f"{len(items)} of your changes {'replace lines' if many else 'replaces a line'} I wrote. "
             f"Add {'them' if many else 'it'} to your Never again list?\n"]
    for i, (doc, c) in enumerate(items, 1):  # Telegram parses HTML: escape draft text
        fix = f'\n   → "{html.escape(c.new)}"' if c.new else "\n   → cut"
        lines.append(f'{i}. ({doc}) "{html.escape(c.old)}"{fix}')
    lines.append("\nReply <b>all</b>, <b>none</b>, or the numbers to add (like 1, 3).")
    return "\n".join(lines)


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
