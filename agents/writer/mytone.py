"""Append a new voice rule to the Notion mytone page (when Liam approves one)."""

from __future__ import annotations

from shared.notion import NotionClient


def append_rule(notion: NotionClient, rule: str) -> None:
    pid = notion.load_ids().get("mytone")
    if not pid:
        raise RuntimeError("mytone page id not found.")
    notion._request("PATCH", f"/blocks/{pid}/children", {"children": [
        {"object": "block", "type": "bulleted_list_item",
         "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": rule[:1900]}}]}}
    ]})
