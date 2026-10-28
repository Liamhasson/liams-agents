"""Integration test: databases exist, and a job can be written, read, deduped.

Skipped automatically when NOTION_TOKEN / NOTION_ROOT_PAGE_ID are not set, so it
is safe in environments without Notion access. Run it where the secrets exist.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.models import Job
from shared.notion import NotionClient
from shared.notion.client import plain_title

HAS_NOTION = bool(os.environ.get("NOTION_TOKEN") and os.environ.get("NOTION_ROOT_PAGE_ID"))

try:
    import pytest
    skip = pytest.mark.skipif(not HAS_NOTION, reason="NOTION_TOKEN/ROOT_PAGE_ID not set")
except ImportError:  # allow running without pytest installed
    def skip(fn):
        return fn


@skip
def test_databases_exist_and_job_roundtrips():
    client = NotionClient()
    ids = client.ensure_databases()
    for name in ("Jobs", "Freelance Leads", "Sources", "Companies"):
        assert name in ids and ids[name], f"missing database: {name}"

    jobs_db = ids["Jobs"]
    job = Job(
        title="TEST — pytest roundtrip (safe to delete)",
        company="Pytest Fixtures Ltd",
        ats="lever", company_slug="pytestfixtures", job_id="rt-1",
        source="pytest",
    )
    page, created = client.upsert_job(jobs_db, job)
    try:
        assert created
        fetched = client.get_page(page["id"])
        assert plain_title(fetched) == job.title

        page2, created2 = client.upsert_job(jobs_db, job)
        assert not created2
        assert page2["id"] == page["id"]
    finally:
        client.archive_page(page["id"])


if __name__ == "__main__":
    if not HAS_NOTION:
        print("SKIP: NOTION_TOKEN/NOTION_ROOT_PAGE_ID not set")
    else:
        test_databases_exist_and_job_roundtrips()
        print("  ✓ integration roundtrip passed")
