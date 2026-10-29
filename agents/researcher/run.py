"""The Researcher.

For Approved jobs without research notes: read the job post + fetch the company
page, then use Sonnet to write concise, factual notes to Notion — what they do,
the problem behind the hire, their values/language, and how Liam fits.

    python -m agents.researcher.run              # all Approved jobs needing notes
    python -m agents.researcher.run --limit 1
    python -m agents.researcher.run --dry-run
"""

from __future__ import annotations

import argparse
import re

from shared import usage
from shared.claude import Claude, SONNET
from shared.http import PoliteClient
from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_text, plain_url

RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "what_they_do": {"type": "string", "description": "1-2 sentences, factual."},
        "problem_behind_hire": {"type": "string", "description": "Why this role exists now."},
        "values_and_language": {"type": "string", "description": "Tone/values to echo in the application."},
        "recent_news": {"type": "string", "description": "'' if not evident from the text."},
        "how_liam_fits": {"type": "string", "description": "2-3 lines, grounded only in known facts."},
    },
    "required": ["what_they_do", "problem_behind_hire", "values_and_language",
                 "recent_news", "how_liam_fits"],
}

SYSTEM = """You research a company so Liam Hasson (a Berlin product/UX designer)
can tailor his application. Work ONLY from the job post and company page text
provided. Be concise and factual. If something isn't evident, say so briefly —
never invent facts, people, or news. Return via the submit_research tool."""


def _visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch(client: PoliteClient, url: str) -> str:
    if not url:
        return ""
    try:
        return _visible_text(client.get(url).text)[:6000]
    except Exception:
        return ""


def _company_careers_url(notion: NotionClient, companies_db: str, company: str) -> str:
    if not company:
        return ""
    matches = notion.query_database(companies_db, {
        "property": "Name", "title": {"equals": company}})
    return plain_url(matches[0], "Careers URL") if matches else ""


def _notes_text(r: dict) -> str:
    parts = [
        f"<b>What they do:</b> {r['what_they_do']}",
        f"<b>Problem behind the hire:</b> {r['problem_behind_hire']}",
        f"<b>Values & language:</b> {r['values_and_language']}",
    ]
    if r.get("recent_news"):
        parts.append(f"<b>Recent news:</b> {r['recent_news']}")
    parts.append(f"<b>How you fit:</b> {r['how_liam_fits']}")
    return "\n".join(parts)


def _rt(s: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": (s or "")[:1900]}}]}


def run(limit: int | None = None, dry_run: bool = False) -> dict:
    notion = NotionClient()
    ids = notion.ensure_databases()
    jobs_db, companies_db = ids["Jobs"], ids["Companies"]
    if usage.over_limit(notion):
        print("Monthly usage limit reached: research paused (see config/settings.yaml > usage).")
        return {"researched": 0, "paused": True}
    claude = Claude(model=SONNET)
    http = PoliteClient()

    jobs = notion.query_database(jobs_db, {"and": [
        {"property": "Status", "select": {"equals": "Approved"}},
        {"property": "Research notes", "rich_text": {"is_empty": True}},
    ]})
    if limit:
        jobs = jobs[:limit]
    print(f"Researching {len(jobs)} approved job(s)...")

    done = failed = 0
    for page in jobs:
        title, company = plain_title(page), plain_text(page, "Company")
        desc = plain_text(page, "Description")
        job_url = plain_url(page, "URL") or plain_url(page, "Apply URL")
        page_text = _fetch(http, job_url)
        careers = _company_careers_url(notion, companies_db, company)
        page_text = (page_text + "\n\n" + _fetch(http, careers)).strip()

        user = (f"Role: {title}\nCompany: {company}\n\n"
                f"Job description:\n{desc[:4000]}\n\n"
                f"Company/careers page text:\n{page_text[:4000] or '(none fetched)'}")
        try:
            res = claude.json_call(SYSTEM, user, RESEARCH_SCHEMA,
                                   tool_name="submit_research", max_tokens=1200)
        except Exception as e:
            failed += 1
            print(f"  ! research failed for {title[:40]}: {e}")
            continue
        notes = _notes_text(res)
        print(f"\n— {title} @ {company} —\n{notes}\n")
        if not dry_run:
            notion.update_page(page["id"], {"Research notes": _rt(notes)})
        done += 1

    http.close()
    usage.log_run(notion, claude, "researcher")
    print(f"Researcher done → {done} job(s).  {claude.cost_summary()}"
          + ("  [dry-run]" if dry_run else ""))
    if failed and not done:
        raise RuntimeError(f"Every research call failed ({failed}). The jobs are retried next run.")
    return {"researched": done}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Research approved jobs")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)
