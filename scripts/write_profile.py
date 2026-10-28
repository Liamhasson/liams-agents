"""Create the 'Matcher Profile' page under the Notion Private page.

Idempotent: if the page already exists it is reused (your edits are kept) and
its id is recorded. Liam edits this page in Notion to tune the Matcher.

    python scripts/write_profile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402
from shared.notion import NotionClient  # noqa: E402
from agents.matcher.profile import PROFILE_KEY  # noqa: E402

PROFILE_LINES = [
    "Liam — matching profile (edit me to tune the Matcher)",
    "",
    "Who I am: Product/UX designer in Berlin. ~1-2 years focused product/UX "
    "(CareerFoundry 2025-26, Cyvore, Pulse) on top of 7+ years in visual, brand, "
    "graphic and video design. AI-native workflow, ship fast, frontend-aware "
    "(Next.js/Vercel).",
    "Level: junior-to-mid in product design. Roles requiring 5+ years of product "
    "design are an experience gap (flag, don't auto-drop). Senior/Lead/Principal "
    "are usually too senior - lower the score.",
    "Role types I want: product design, UX/UI, web design, brand & visual, growth "
    "design, light design engineering. Open to internships and founder-associate roles.",
    "Avoid: working-student roles.",
    "Location: Berlin (on-site/hybrid) or remote roles that can employ someone "
    "living in Germany. No relocation outside Germany.",
    "Language: English fluent, German A2. Drop roles requiring fluent/business "
    "German. Fine if German is nice-to-have or unmentioned.",
    "Strong fits: AI-native companies, consumer/mobile apps, fast startups, design "
    "systems, brand+product blends, teams that value shipping and frontend skills.",
    "Weaker fits: research-only roles with no UI/visual craft, print-only graphic "
    "roles, senior-only roles needing 5+ yrs product design, heavy enterprise "
    "requiring German.",
    "Dealbreakers: fluent German required; relocation outside Germany. Flag (don't "
    "drop): unpaid, contract.",
]


def _find_private_page(notion: NotionClient, root_id: str) -> str:
    blocks = notion._paginated("GET", f"/blocks/{root_id}/children?page_size=100")
    for b in blocks:
        if b.get("type") == "child_page" and b["child_page"].get("title") == "Private":
            return b["id"]
    raise RuntimeError("Could not find a 'Private' sub-page under 'Liam's agents'.")


def _find_existing_profile(notion: NotionClient, private_id: str) -> str | None:
    blocks = notion._paginated("GET", f"/blocks/{private_id}/children?page_size=100")
    for b in blocks:
        if b.get("type") == "child_page" and b["child_page"].get("title") == PROFILE_KEY:
            return b["id"]
    return None


def main() -> None:
    notion = NotionClient()
    notion.ensure_databases()
    root = config.require("NOTION_ROOT_PAGE_ID")
    private_id = _find_private_page(notion, root)

    existing = _find_existing_profile(notion, private_id)
    if existing:
        notion.save_id(PROFILE_KEY, existing)
        print(f"'{PROFILE_KEY}' already exists — reusing it (your edits kept).")
        print(f"  page id: {existing}")
        return

    children = [
        {"object": "block", "type": "paragraph",
         "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}] if line else []}}
        for line in PROFILE_LINES
    ]
    page = notion._request("POST", "/pages", {
        "parent": {"type": "page_id", "page_id": private_id},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": PROFILE_KEY}}]}},
        "children": children,
    })
    notion.save_id(PROFILE_KEY, page["id"])
    print(f"Created '{PROFILE_KEY}' under Private. Edit it in Notion anytime.")
    print(f"  page id: {page['id']}")


if __name__ == "__main__":
    main()
