"""Create (or reuse) the four Notion databases under the 'Liam's agents' page.

Safe to run repeatedly — existing databases are reused, never duplicated.

    python scripts/init_notion.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import config  # noqa: E402
from shared.notion import NotionClient  # noqa: E402


def main() -> None:
    client = NotionClient()
    root = config.require("NOTION_ROOT_PAGE_ID")
    print("Ensuring databases under the 'Liam's agents' page...\n")
    ids = client.ensure_databases(root)
    for name, db_id in ids.items():
        print(f"  ✓ {name:<16} {db_id}")
    print("\nSaved ids to config/notion_ids.json")
    print("Open your 'Liam's agents' page in Notion — the four databases are now there.")


if __name__ == "__main__":
    main()
