"""Phase 1 demo: prove a job can be written, read back, and de-duplicated.

    python scripts/demo_phase1.py

It writes a clearly-marked TEST job to the Jobs database, reads it back, writes
the SAME job again to show dedupe, then archives the test row so your workspace
stays clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.models import Job  # noqa: E402
from shared.notion import NotionClient  # noqa: E402
from shared.notion.client import plain_title, plain_text  # noqa: E402


def main() -> None:
    client = NotionClient()
    ids = client.ensure_databases()
    jobs_db = ids["Jobs"]

    job = Job(
        title="TEST — Phase 1 Dedupe Check (safe to delete)",
        company="Acme Test GmbH",
        url="https://example.com/jobs/phase1-test",
        source="demo",
        ats="greenhouse",
        company_slug="acmetest",
        job_id="phase1-0001",
        location="Berlin, Germany",
        remote="hybrid",
        role_type="product design",
    )
    print(f"Job dedupe key: {job.dedupe_key}")

    print("\n[1] Writing test job...")
    page, created = client.upsert_job(jobs_db, job)
    assert created, "expected a fresh write"
    page_id = page["id"]
    print(f"    ✓ created page {page_id}")

    print("[2] Reading it back...")
    fetched = client.get_page(page_id)
    title = plain_title(fetched)
    company = plain_text(fetched, "Company")
    print(f"    ✓ read: {title!r} @ {company!r}")
    assert title == job.title and company == job.company

    print("[3] Writing the SAME job again (should dedupe, not duplicate)...")
    page2, created2 = client.upsert_job(jobs_db, job)
    assert not created2, "expected dedupe (no second row)"
    assert page2["id"] == page_id, "dedupe should point at the same row"
    print(f"    ✓ deduped → same page {page2['id']} (no duplicate created)")

    print("[4] Cleaning up (archiving the test row)...")
    client.archive_page(page_id)
    print("    ✓ archived")

    print("\nPhase 1 demo passed: write ✓  read ✓  dedupe ✓")


if __name__ == "__main__":
    main()
