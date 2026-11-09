"""The Researcher.

For a job Liam wants to be briefed on: read the job post and the company's own
website, then use Sonnet to write concise, factual notes to Notion: what they do,
the problem behind the hire, and their values and language. Facts about the
company only. How Liam fits is the Director's job.

    python -m agents.researcher.run --job <id>   # one job
    python -m agents.researcher.run              # all Approved jobs needing notes
    python -m agents.researcher.run --limit 1
    python -m agents.researcher.run --dry-run
"""

from __future__ import annotations

import argparse
import re
from urllib.parse import urlparse

from shared import usage
from shared.claude import Claude, SONNET
from shared.http import PoliteClient
from shared.notion import NotionClient
from shared.notion.client import _long_rt, plain_title, plain_text, plain_url

RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "what_they_do": {"type": "string", "description": "1-2 sentences, factual."},
        "problem_behind_hire": {"type": "string", "description": "Why this role exists now."},
        "values_and_language": {"type": "string", "description": "Tone/values to echo in the application."},
        "recent_news": {"type": "string", "description": "'' if not evident from the text."},
    },
    "required": ["what_they_do", "problem_behind_hire", "values_and_language",
                 "recent_news"],
}

SYSTEM = """You research a company so Liam Hasson (a Berlin product/UX designer)
can tailor his application. Work ONLY from the job post and company website text
provided. Be concise and factual. If something isn't evident, say so briefly —
never invent facts, people, or news. Return via the submit_research tool."""


def _visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Hiring tools host job pages for many companies, so their address says nothing about the company.
_HIRING_TOOLS = ("ashbyhq.com", "greenhouse.io", "lever.co", "workable.com", "personio.de", "personio.com",
                 "recruitee.com", "smartrecruiters.com", "teamtailor.com", "join.com")


def website_url(job_page_html: str, careers_url: str) -> str:
    """The company's own site: from the hiring page's data if it says, else from the Careers URL."""
    found = re.search(r'"publicWebsite"\s*:\s*"(https?://[^"]+)"', job_page_html or "")
    if found:
        return found.group(1)
    parts = urlparse(careers_url or "")
    if not parts.netloc or any(parts.netloc.endswith(host) for host in _HIRING_TOOLS):
        return ""
    return f"{parts.scheme}://{parts.netloc}/"


def _html(client: PoliteClient, url: str) -> str:
    if not url:
        return ""
    try:
        return client.get(url).text
    except Exception:  # includes a robots.txt refusal: that page counts as not read
        return ""


def read_site(client: PoliteClient, url: str) -> str:
    return _visible_text(_html(client, url))[:6000]


def _company_careers_url(notion: NotionClient, companies_db: str, company: str) -> str:
    if not company:
        return ""
    matches = notion.query_database(companies_db, {
        "property": "Name", "title": {"equals": company}})
    return plain_url(matches[0], "Careers URL") if matches else ""


def _notes_text(r: dict, site_read: bool = True) -> str:
    parts = [
        f"<b>What they do:</b> {r['what_they_do']}",
        f"<b>Problem behind the hire:</b> {r['problem_behind_hire']}",
        f"<b>Values & language:</b> {r['values_and_language']}",
    ]
    if r.get("recent_news"):
        parts.append(f"<b>Recent news:</b> {r['recent_news']}")
    if not site_read:
        parts.append("<i>The company's website wasn't read.</i>")
    return "\n".join(parts)


def run(limit: int | None = None, dry_run: bool = False, job_id: str | None = None) -> dict:
    notion = NotionClient()
    ids = notion.ensure_databases()
    jobs_db, companies_db = ids["Jobs"], ids["Companies"]
    if usage.over_limit(notion):
        print("Monthly usage limit reached: research paused (see config/settings.yaml > usage).")
        return {"researched": 0, "paused": True}
    claude = Claude(model=SONNET)
    http = PoliteClient()

    if job_id:
        page = notion.get_page(job_id)
        jobs = [] if plain_text(page, "Research notes") else [page]
    else:
        jobs = notion.query_database(jobs_db, {"and": [
            {"property": "Status", "select": {"equals": "Approved"}},
            {"property": "Research notes", "rich_text": {"is_empty": True}},
        ]})
    if limit:
        jobs = jobs[:limit]
    print(f"Researching {len(jobs)} approved job(s)...")

    done = failed = 0
    notes = ""
    for page in jobs:
        title, company = plain_title(page), plain_text(page, "Company")
        desc = plain_text(page, "Description")
        job_url = plain_url(page, "URL") or plain_url(page, "Apply URL")
        job_html = _html(http, job_url)
        careers = _company_careers_url(notion, companies_db, company)
        careers_text = read_site(http, careers)
        site_text = read_site(http, website_url(job_html, careers))

        user = (f"Role: {title}\nCompany: {company}\n\n"
                f"Job description:\n{desc[:6000]}\n\n"
                f"Careers page text:\n{careers_text[:3000] or '(none fetched)'}\n\n"
                f"Company website text:\n{site_text[:4000] or '(not read)'}")
        try:
            res = claude.json_call(SYSTEM, user, RESEARCH_SCHEMA,
                                   tool_name="submit_research", max_tokens=1200)
        except Exception as e:
            failed += 1
            print(f"  ! research failed for {title[:40]}: {e}")
            continue
        notes = _notes_text(res, site_read=bool(site_text))
        if dry_run:  # Actions logs are public, so a real run doesn't print which job Liam chose
            print(f"\n— {title} @ {company} —\n{notes}\n")
        if not dry_run:
            notion.update_page(page["id"], {"Research notes": _long_rt(notes)})
        done += 1

    http.close()
    usage.log_run(notion, claude, "researcher")
    print(f"Researcher done → {done} job(s).  {claude.cost_summary()}"
          + ("  [dry-run]" if dry_run else ""))
    if failed and not done:
        raise RuntimeError(f"Every research call failed ({failed}). The jobs are retried next run.")
    return {"researched": done, "notes": notes}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Research approved jobs")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--job", default=None, help="Notion job page id")
    args = ap.parse_args()
    run(limit=args.limit, dry_run=args.dry_run, job_id=args.job)
