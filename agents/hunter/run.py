"""The Hunter runner.

Reads active Companies (ATS) and active Sources (feeds) from Notion, fetches
each politely, keeps design-relevant titles, and upserts into the Jobs database
(Phase 1 dedupe prevents duplicates). Updates per-source stats as it goes.

    python -m agents.hunter.run            # live
    python -m agents.hunter.run --dry-run  # fetch + report, write nothing
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from shared.http import PoliteClient
from shared.notion import NotionClient
from shared.notion.client import (
    plain_title, plain_text, plain_select, plain_number,
)
from .registry import ATS_ADAPTERS, FEEDS
from .relevance import title_passes

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_hunter_cfg() -> dict:
    return yaml.safe_load(_CONFIG.read_text()).get("hunter", {})


def run(dry_run: bool = False) -> dict:
    cfg = _load_hunter_cfg()
    client = PoliteClient(min_interval=float(cfg.get("min_interval_seconds", 1.0)))
    notion = NotionClient()
    ids = notion.ensure_databases()
    jobs_db, companies_db, sources_db = ids["Jobs"], ids["Companies"], ids["Sources"]

    collected: list[tuple] = []  # (job, origin_page_id)

    # --- Companies (ATS boards) ---
    companies = notion.query_database(companies_db, {"property": "Active", "checkbox": {"equals": True}})
    print(f"Active companies: {len(companies)}")
    for c in companies:
        name, ats, slug = plain_title(c), plain_select(c, "ATS"), plain_text(c, "ATS slug")
        adapter = ATS_ADAPTERS.get(ats)
        if not adapter or not slug:
            continue
        try:
            jobs = adapter(client, slug, name)
        except Exception as e:
            print(f"  ! {name} ({ats}:{slug}) failed: {e}")
            jobs = []
        for j in jobs:
            collected.append((j, c["id"]))

    # --- Feeds (active Sources) ---
    sources = notion.query_database(sources_db, {"property": "Status", "select": {"equals": "active"}})
    print(f"Active feed sources: {len(sources)}")
    for s in sources:
        name = plain_title(s)
        feed = FEEDS.get(name)
        if not feed:
            continue
        try:
            jobs = feed["fetch"](client, feed["endpoint"], name, **feed.get("kwargs", {}))
        except Exception as e:
            print(f"  ! feed {name} failed: {e}")
            jobs = []
        for j in jobs:
            collected.append((j, s["id"]))

    # --- Filter + upsert ---
    kept = [(j, pid) for (j, pid) in collected if title_passes(j.title, cfg)]
    print(f"\nCollected {len(collected)} jobs, {len(kept)} pass the design title gate.")

    created = deduped = 0
    found_by_origin: dict[str, int] = {}
    new_by_origin: dict[str, int] = {}
    for j, pid in kept:
        found_by_origin[pid] = found_by_origin.get(pid, 0) + 1
        if dry_run:
            continue
        _page, was_created = notion.upsert_job(jobs_db, j)
        if was_created:
            created += 1
            new_by_origin[pid] = new_by_origin.get(pid, 0) + 1
        else:
            deduped += 1

    # --- Update stats (skip in dry-run) ---
    if not dry_run:
        now = _now()
        for c in companies:
            props = {"Last checked": {"date": {"start": now}}}
            if new_by_origin.get(c["id"]):
                props["Last new job at"] = {"date": {"start": now}}
            notion.update_page(c["id"], props)
        for s in sources:
            prev = plain_number(s, "Jobs found") or 0
            notion.update_page(s["id"], {
                "Jobs found": {"number": prev + found_by_origin.get(s["id"], 0)},
                "Last checked": {"date": {"start": now}},
            })

    client.close()
    summary = {"collected": len(collected), "kept": len(kept), "created": created, "deduped": deduped}
    print(f"\nHunter done → created {created} new, {deduped} already seen (deduped)."
          + ("  [dry-run: nothing written]" if dry_run else ""))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="The Hunter — collect new jobs into Notion")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
