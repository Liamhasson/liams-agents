"""Create the Writer's "Never again" database under Notion Private (idempotent).

    python scripts/setup_never_again.py

Saves the database id to config/notion_ids.json as "Never again". Entries are
added by the Writer only after Liam confirms them on Telegram.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from agents.writer.context import _private_page_id
from shared.notion import NotionClient
from shared.notion.schema import NEVER_AGAIN_SCHEMA

NAME = "Never again"


def main() -> None:
    load_dotenv(override=True)
    notion = NotionClient()
    private = _private_page_id(notion)
    if not private:
        raise SystemExit("No 'Private' page under the root page.")
    existing = notion.find_databases_under(private)
    if NAME in existing:
        db_id = existing[NAME]
        notion._add_missing_properties(db_id, NEVER_AGAIN_SCHEMA)
        print(f"Reusing '{NAME}': {db_id}")
    else:
        db_id = notion.create_database(private, NAME, NEVER_AGAIN_SCHEMA)
        print(f"Created '{NAME}': {db_id}")
    notion.save_id(NAME, db_id)


if __name__ == "__main__":
    main()
