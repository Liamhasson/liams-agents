"""Add to the Notion mytone page."""

from __future__ import annotations

import re

from shared.notion import NotionClient


def append_rule(notion: NotionClient, rule: str) -> None:
    pid = notion.load_ids().get("mytone")
    if not pid:
        raise RuntimeError("mytone page id not found.")
    notion._request("PATCH", f"/blocks/{pid}/children", {"children": [
        {"object": "block", "type": "bulleted_list_item",
         "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": rule[:1900]}}]}}
    ]})


CORRECTIONS_HEADING = "14. Corrections from the Editor"


def _block(kind: str, text: str) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]}}


def append_correction(notion: NotionClient, line: str) -> None:
    """One bullet under the Corrections heading, which is added the first time."""
    pid = notion.load_ids().get("mytone")
    if not pid:
        raise RuntimeError("mytone page id not found.")
    children = [] if CORRECTIONS_HEADING in notion.page_text(pid) else [_block("paragraph", CORRECTIONS_HEADING)]
    children.append(_block("bulleted_list_item", line))
    notion._request("PATCH", f"/blocks/{pid}/children", {"children": children})


_REJECTED = re.compile(r'^\[[^\]]*\] (Instead of|About) "')


def without_rejected(guide: str) -> str:
    """The guide minus corrections that quote a line Liam threw out, so a rejected line can never count as proof."""
    return "\n".join(line for line in guide.splitlines() if not _REJECTED.match(line.strip()))
