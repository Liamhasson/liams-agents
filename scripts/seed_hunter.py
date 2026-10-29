"""Seed the Sources (feeds) and Companies (ATS) databases for the Hunter.

Idempotent: rows are matched by name and skipped if they already exist, so you
can run it repeatedly and add new seeds over time.

    python scripts/seed_hunter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hunter.registry import FEEDS  # noqa: E402
from shared.notion import NotionClient  # noqa: E402
from shared.notion.client import plain_title  # noqa: E402

# Verified live (Oct 2026). Berlin/EU-focused, with a few high-volume design
# teams for variety. Liam can add his own targets as rows in the Companies DB.
SEED_COMPANIES = [
    ("greenhouse", "n26", "N26", "https://n26.com/en/careers"),
    ("greenhouse", "hellofresh", "HelloFresh", "https://www.hellofresh.com/careers/"),
    ("greenhouse", "getyourguide", "GetYourGuide", "https://careers.getyourguide.com/"),
    ("greenhouse", "raisin", "Raisin", "https://www.raisin.com/careers/"),
    ("greenhouse", "contentful", "Contentful", "https://www.contentful.com/careers/"),
    ("greenhouse", "celonis", "Celonis", "https://www.celonis.com/careers/jobs/"),
    ("greenhouse", "moonfare", "Moonfare", "https://www.moonfare.com/careers"),
    ("ashby", "pennylane", "Pennylane", "https://www.pennylane.com/careers"),
    ("ashby", "qonto", "Qonto", "https://qonto.com/en/careers"),
    ("ashby", "linear", "Linear", "https://linear.app/careers"),
    ("ashby", "notion", "Notion", "https://www.notion.so/careers"),
    ("personio", "personio", "Personio", "https://www.personio.com/careers/"),
    # Berlin companies (added Oct 2026, Berlin-first search). Careers URL is their job board.
    ("ashby", "babbel", "Babbel", "https://jobs.ashbyhq.com/babbel"),
    ("greenhouse", "sumup", "SumUp", "https://job-boards.greenhouse.io/sumup"),
    ("ashby", "moss", "Moss", "https://jobs.ashbyhq.com/moss"),
    ("greenhouse", "parloa", "Parloa", "https://job-boards.greenhouse.io/parloa"),
    ("ashby", "zenjob", "Zenjob", "https://jobs.ashbyhq.com/zenjob"),
    ("ashby", "knowunity", "Knowunity", "https://jobs.ashbyhq.com/knowunity"),
    ("ashby", "langdock", "Langdock", "https://jobs.ashbyhq.com/langdock"),
    ("greenhouse", "wooga", "Wooga", "https://job-boards.greenhouse.io/wooga"),
    ("greenhouse", "doctolib", "Doctolib", "https://job-boards.greenhouse.io/doctolib"),
    ("ashby", "n8n", "n8n", "https://jobs.ashbyhq.com/n8n"),
    ("greenhouse", "traderepublicbank", "Trade Republic", "https://job-boards.greenhouse.io/traderepublicbank"),
    ("ashby", "upvest", "Upvest", "https://jobs.ashbyhq.com/upvest"),
    ("greenhouse", "grover", "Grover", "https://job-boards.greenhouse.io/grover"),
    ("greenhouse", "solarisbank", "Solaris", "https://job-boards.greenhouse.io/solarisbank"),
    ("greenhouse", "superchat", "Superchat", "https://job-boards.greenhouse.io/superchat"),
    ("ashby", "buena", "Buena", "https://jobs.ashbyhq.com/buena"),
    ("ashby", "pliant", "Pliant", "https://jobs.ashbyhq.com/pliant"),
    ("ashby", "ostrom", "Ostrom", "https://jobs.ashbyhq.com/ostrom"),
    ("ashby", "tourlane", "Tourlane", "https://jobs.ashbyhq.com/tourlane"),
    ("personio", "everphone", "Everphone", "https://everphone.jobs.personio.de"),
    ("personio", "1komma5grad", "1Komma5°", "https://1komma5grad.jobs.personio.de"),
    ("greenhouse", "helsing", "Helsing", "https://job-boards.greenhouse.io/helsing"),
]


def _title(s: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": s}}]}


def _rt(s: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": s}}]}


def main() -> None:
    notion = NotionClient()
    ids = notion.ensure_databases()
    sources_db, companies_db = ids["Sources"], ids["Companies"]

    # --- Sources (feeds) ---
    existing_sources = {plain_title(p) for p in notion.query_database(sources_db)}
    print("Seeding feed sources...")
    for name, feed in FEEDS.items():
        if name in existing_sources:
            print(f"  · {name} (exists)")
            continue
        notion.create_page(sources_db, {
            "Name": _title(name),
            "Type": {"select": {"name": feed["type"]}},
            "Access": {"select": {"name": feed["access"]}},
            "Endpoint": _rt(feed["endpoint"]),
            "Status": {"select": {"name": "active"}},
            "Notes on terms": _rt(feed["notes"]),
        })
        print(f"  ✓ {name}")

    # --- Companies (ATS) ---
    existing_companies = {plain_title(p) for p in notion.query_database(companies_db)}
    print("\nSeeding companies...")
    for ats, slug, name, careers in SEED_COMPANIES:
        if name in existing_companies:
            print(f"  · {name} (exists)")
            continue
        notion.create_page(companies_db, {
            "Name": _title(name),
            "Careers URL": {"url": careers},
            "ATS": {"select": {"name": ats}},
            "ATS slug": _rt(slug),
            "Found via": _rt("seed"),
            "Active": {"checkbox": True},
        })
        print(f"  ✓ {name} ({ats}:{slug})")

    print("\nSeeded. Run the Hunter with:  python -m agents.hunter.run")


if __name__ == "__main__":
    main()
