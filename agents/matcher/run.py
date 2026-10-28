"""The Matcher runner.

Scores unscored "New" jobs against Liam's profile, applies hard filters and
score thresholds, and writes the result back to Notion.

    python -m agents.matcher.run                 # score all unscored New jobs
    python -m agents.matcher.run --limit 20      # just the first 20 (tuning)
    python -m agents.matcher.run --limit 20 --rescore   # re-score even if scored
    python -m agents.matcher.run --limit 20 --dry-run   # print, write nothing
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from shared.claude import Claude
from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_text, plain_select
from shared.notion.schema import ROLE_TYPES
from .profile import load_profile
from .score import score, route, is_hard_drop

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def _rt(s: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": (s or "")[:1900]}}]}


def _cfg() -> dict:
    return yaml.safe_load(_CONFIG.read_text()).get("matcher", {})


def run(limit: int | None = None, rescore: bool = False, dry_run: bool = False) -> dict:
    cfg = _cfg()
    alert = int(cfg.get("alert_threshold", 70))
    ask = int(cfg.get("ask_threshold", 40))
    hard_drops = [k.lower() for k in cfg.get("hard_drop_title_keywords", [])]

    notion = NotionClient()
    ids = notion.ensure_databases()
    jobs_db = ids["Jobs"]
    profile = load_profile(notion)
    claude = Claude()

    if rescore:
        flt = {"property": "Status", "select": {"equals": "New"}}
    else:
        flt = {"and": [
            {"property": "Status", "select": {"equals": "New"}},
            {"property": "Score", "number": {"is_empty": True}},
        ]}
    jobs = notion.query_database(jobs_db, flt)
    if limit:
        jobs = jobs[:limit]
    print(f"Scoring {len(jobs)} job(s)  (alert>={alert}, ask>={ask})\n")

    counts = {"alert": 0, "ask": 0, "dropped": 0}
    results = []
    for page in jobs:
        title = plain_title(page)
        company = plain_text(page, "Company")
        desc = plain_text(page, "Description")
        location = plain_text(page, "Location")
        remote = plain_select(page, "Remote")

        # Deterministic hard drop (working-student etc.) — saves a Claude call.
        if is_hard_drop(title, desc, hard_drops):
            decision, reason, sc = "dropped", "working-student role", 0
            res = {"score": 0, "role_type": "other", "fit_summary": "", "why_you": "",
                   "gaps": "", "flags": [], "german_required": "none", "remote_eligibility": "unclear"}
        else:
            try:
                res = score(claude, profile, title=title, company=company,
                            location=location, remote=remote, description=desc)
            except Exception as e:
                print(f"  ! scoring failed for {title[:40]}: {e}")
                continue
            sc = int(res["score"])
            decision, reason = route(res, alert, ask)

        flags = list(res.get("flags", []))
        if decision == "ask" and "borderline" not in flags:
            flags.append("borderline")
        status = "Skipped" if decision == "dropped" else "New"
        fit = res["fit_summary"]
        if reason:
            fit = f"[dropped: {reason}] {fit}".strip()

        counts[decision] += 1
        results.append((sc, decision, title, company, flags, res, reason))

        if not dry_run:
            props = {
                "Score": {"number": sc},
                "Fit summary": _rt(fit),
                "Why Liam": _rt(res["why_you"]),
                "Gaps": _rt(res["gaps"]),
                "Flags": {"multi_select": [{"name": f} for f in flags]},
                "German required": {"select": {"name": res["german_required"]}},
                "Remote eligibility": {"select": {"name": res["remote_eligibility"]}},
                "Status": {"select": {"name": status}},
            }
            if res["role_type"] in ROLE_TYPES:
                props["Role type"] = {"select": {"name": res["role_type"]}}
            notion.update_page(page["id"], props)

    _print_report(results)
    print(f"\nMatcher done → {counts['alert']} alert, {counts['ask']} ask, "
          f"{counts['dropped']} dropped.  {claude.cost_summary()}"
          + ("  [dry-run: nothing written]" if dry_run else ""))
    return {"counts": counts, "results": results}


def _print_report(results: list) -> None:
    for sc, decision, title, company, flags, res, reason in sorted(results, key=lambda r: -r[0]):
        tag = {"alert": "🟢", "ask": "🟡", "dropped": "⚪️"}[decision]
        line = f"{tag} {sc:>3}  {title[:38]:<38} @ {company[:18]:<18}"
        extra = []
        if flags:
            extra.append("flags=" + ",".join(flags))
        if res.get("german_required") == "fluent":
            extra.append("DE-fluent")
        if reason:
            extra.append(reason)
        print(line + ("   " + " · ".join(extra) if extra else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="The Matcher — score jobs against Liam's profile")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rescore", action="store_true", help="re-score New jobs even if already scored")
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = ap.parse_args()
    run(limit=args.limit, rescore=args.rescore, dry_run=args.dry_run)
