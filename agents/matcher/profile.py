"""Load Liam's matching profile from the Notion Private page.

The profile lives in a Notion page so Liam can edit it himself. Its page id is
stored in config/notion_ids.json by scripts/write_profile.py.
"""

from __future__ import annotations

from shared.notion import NotionClient

PROFILE_KEY = "Matcher Profile"


def load_profile(notion: NotionClient) -> str:
    ids = notion.load_ids()
    page_id = ids.get(PROFILE_KEY)
    if not page_id:
        raise RuntimeError(
            "Matcher profile not set up yet. Run: python scripts/write_profile.py"
        )
    blocks = notion._paginated("GET", f"/blocks/{page_id}/children?page_size=100")
    lines: list[str] = []
    for b in blocks:
        btype = b.get("type", "")
        body = b.get(btype, {})
        rt = body.get("rich_text", []) if isinstance(body, dict) else []
        text = "".join(x.get("plain_text", "") for x in rt)
        if text.strip():
            lines.append(text)
    if not lines:
        raise RuntimeError("Matcher profile page is empty.")
    return "\n".join(lines)
