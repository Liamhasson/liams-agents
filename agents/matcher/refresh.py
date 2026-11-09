"""Recalculate the points for post age once a day. No model calls, no messages.

A job gets points for how new it is, and those should fade as it gets older. This
only changes the order jobs are listed in. It never sends a card again.

    python -m agents.matcher.refresh
    python -m agents.matcher.refresh --dry-run
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import yaml

from shared.notion.client import _rt, plain_date, plain_number, plain_select, plain_text
from .score import age_points, freshness

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
_AGE_LABELS = ("new post", "old post")


def refreshed(base: int, fit: int, posted_at: str, now_iso: str, rules: dict) -> tuple[int, str]:
    """The score at this moment, and the age part of its breakdown ('' if there's none)."""
    age = age_points(posted_at, now_iso, rules.get("age_points") or {}, int(rules.get("age_points_after", 0)))
    if age > 0 and fit < int(rules.get("bonus_min_fit", 0)):
        age = 0  # same rule as the first score: bonuses only go to jobs that already fit
    part = "" if age == 0 else f"{'new post' if age > 0 else 'old post'} {age:+d}"
    return max(0, int(base) + age), part


def with_age(breakdown: str, part: str) -> str:
    """Swap the age part of a breakdown, keeping it before the years part."""
    pieces = [p for p in breakdown.split(" · ") if p and not p.startswith(_AGE_LABELS)]
    if part:
        at = next((i for i, p in enumerate(pieces) if p.startswith("asks ")), len(pieces))
        pieces.insert(at, part)
    return " · ".join(pieces)


def apply(notion, jobs_db: str, statuses: list[str], rules: dict, now_iso: str, dry_run: bool = False) -> dict:
    rows = notion.query_database(jobs_db, {"or": [
        {"property": "Status", "select": {"equals": s}} for s in statuses]})
    changed = 0
    for page in rows:
        base = plain_number(page, "Base score")
        if base is None:
            continue  # scored before this existed
        fit = plain_number(page, "Fit score") or 0
        posted = plain_date(page, "Posted at")
        score, part = refreshed(int(base), int(fit), posted, now_iso, rules)
        priority = freshness(posted, now_iso)
        if score == plain_number(page, "Score") and priority == plain_select(page, "Priority"):
            continue
        changed += 1
        if not dry_run:
            notion.update_page(page["id"], {
                "Score": {"number": score},
                "Priority": {"select": {"name": priority}},
                "Score breakdown": _rt(with_age(plain_text(page, "Score breakdown"), part)),
            })
    return {"refreshed": changed}


def run(dry_run: bool = False) -> dict:
    from shared.notion import NotionClient

    cfg = yaml.safe_load(_CONFIG.read_text())
    notion = NotionClient()
    jobs_db = notion.ensure_databases()["Jobs"]
    statuses = (cfg.get("messenger") or {}).get("awaiting_statuses", ["Waiting for Liam", "Asked Liam"])
    result = apply(notion, jobs_db, statuses, cfg.get("matcher", {}),
                   datetime.now(timezone.utc).isoformat(), dry_run)
    print(f"Refreshed {result['refreshed']} job(s)." + ("  [dry-run]" if dry_run else ""))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Recalculate the points for post age")
    ap.add_argument("--dry-run", action="store_true")
    run(dry_run=ap.parse_args().dry_run)
