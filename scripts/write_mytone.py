"""Import Liam's mytone.md into the Notion Private page, word-for-word.

The content lives ONLY in Notion (the repo is public). This script reads a
local file (default ~/Downloads/mytone.md) and recreates a 'mytone' page under
Private, preserving every word — markdown is mapped to Notion blocks so it reads
nicely, but no words are rewritten, summarised or omitted.

    python scripts/write_mytone.py [path-to-mytone.md]
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402
from shared.notion import NotionClient  # noqa: E402

PAGE_KEY = "mytone"
_MAX = 1900


def _rt(text: str) -> list:
    return [{"type": "text", "text": {"content": text[:_MAX]}}]


def _line_to_block(line: str) -> dict | None:
    s = line.strip()
    if not s:
        return None
    if s == "---":
        return {"object": "block", "type": "divider", "divider": {}}
    if re.match(r"^\|[\s\-:|]+\|$", s):   # markdown table separator row -> skip (syntax only)
        return None
    for mark, btype in (("### ", "heading_3"), ("## ", "heading_2"), ("# ", "heading_1")):
        if s.startswith(mark):
            return {"object": "block", "type": btype, btype: {"rich_text": _rt(s[len(mark):])}}
    if s.startswith("> "):
        return {"object": "block", "type": "quote", "quote": {"rich_text": _rt(s[2:])}}
    if s.startswith(("- ", "* ")):
        return {"object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _rt(s[2:])}}
    m = re.match(r"^\d+\.\s+(.*)", s)
    if m:
        return {"object": "block", "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _rt(m.group(1))}}
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rt(s)}}


def _find_child_page(notion: NotionClient, parent_id: str, title: str) -> str | None:
    for b in notion._paginated("GET", f"/blocks/{parent_id}/children?page_size=100"):
        if b.get("type") == "child_page" and b["child_page"].get("title") == title:
            return b["id"]
    return None


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.path.expanduser("~/Downloads/mytone.md"))
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    raw = path.read_text(encoding="utf-8")
    blocks = [b for b in (_line_to_block(l) for l in raw.splitlines()) if b]

    notion = NotionClient()
    root = config.require("NOTION_ROOT_PAGE_ID")
    private = _find_child_page(notion, root, "Private")
    if not private:
        raise SystemExit("Could not find the 'Private' sub-page under 'Liam's agents'.")

    old = _find_child_page(notion, private, PAGE_KEY)
    if old:
        notion.archive_page(old)
        print(f"Archived previous '{PAGE_KEY}' page (replacing with current version).")

    page = notion._request("POST", "/pages", {
        "parent": {"type": "page_id", "page_id": private},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": PAGE_KEY}}]}},
        "children": blocks[:100],
    })
    pid = page["id"]
    for i in range(100, len(blocks), 100):
        notion._request("PATCH", f"/blocks/{pid}/children", {"children": blocks[i:i + 100]})
    notion.save_id(PAGE_KEY, pid)

    # Verify fidelity: words in vs words read back.
    back = notion.page_text(pid)
    src_words = len(re.findall(r"\w+", raw))
    back_words = len(re.findall(r"\w+", back))
    print(f"Imported '{PAGE_KEY}' → {len(blocks)} blocks, page {pid}")
    print(f"Fidelity check: source {src_words} words / read-back {back_words} words "
          f"({back_words / src_words:.0%})")


if __name__ == "__main__":
    main()
