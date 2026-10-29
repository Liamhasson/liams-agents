"""Notion database schemas for Liam's agents (BUILD_BRIEF.md §6).

Each schema is the `properties` payload for Notion's "create a database" API.
Exactly one property per database must be of type `title`.

DATABASES maps a database name to its schema. init_notion.py creates/reuses a
Notion database per entry under the root "Liam's agents" page.
"""

from __future__ import annotations


def _select(*names: str) -> dict:
    return {"select": {"options": [{"name": n} for n in names]}}


def _multi(*names: str) -> dict:
    return {"multi_select": {"options": [{"name": n} for n in names]}}


ATS_OPTIONS = [
    "greenhouse", "lever", "ashby", "personio", "workable", "recruitee",
    "teamtailor", "join", "smartrecruiters", "workday", "other",
]

ROLE_TYPES = [
    "product design", "UX/UI", "web design", "brand or visual", "growth design",
    "design engineer", "internship", "working student", "founder associate", "other",
]

JOB_STATUSES = [
    "New", "Asked Liam", "Waiting for Liam", "Approved", "Drafting",
    "Ready to send", "Applied", "Needs Liam to submit", "Interview", "Offer",
    "Rejected", "Skipped", "Expired",
]

JOB_FLAGS = ["senior", "experience gap", "borderline", "contract", "unpaid", "ghost"]


JOBS_SCHEMA: dict = {
    "Title": {"title": {}},
    "Company": {"rich_text": {}},
    "URL": {"url": {}},
    "Apply URL": {"url": {}},
    "Source": {"rich_text": {}},
    "Company ATS": _select(*ATS_OPTIONS),
    "Location": {"rich_text": {}},
    "Remote": _select("yes", "no", "hybrid"),
    "Posted at": {"date": {}},
    "First seen at": {"date": {}},
    "Role type": _select(*ROLE_TYPES),
    "Description": {"rich_text": {}},
    "German required": _select("none", "basic", "fluent"),
    "Remote eligibility": _select("berlin", "remote_de_ok", "unclear", "no"),
    "Priority": _select("fresh", "recent", "older"),
    "Ghost risk": _select("low", "medium", "high"),
    "Ghost reason": {"rich_text": {}},
    "Times seen": {"number": {"format": "number"}},
    "Last seen at": {"date": {}},
    "Score": {"number": {"format": "number"}},
    "Fit summary": {"rich_text": {}},
    "Why Liam": {"rich_text": {}},
    "Gaps": {"rich_text": {}},
    "Flags": _multi(*JOB_FLAGS),
    "Status": _select(*JOB_STATUSES),
    "Apply method": _select("email", "ATS form", "manual"),
    "Last reminder at": {"date": {}},
    "Reminder count": {"number": {"format": "number"}},
    "Telegram message id": {"number": {"format": "number"}},
    "Research notes": {"rich_text": {}},
    "CV draft": {"rich_text": {}},
    "Cover letter draft": {"rich_text": {}},
    "Lines changed": {"number": {"format": "number"}},  # Liam's edits to the first draft
    "Final PDFs": {"files": {}},
    "Applied at": {"date": {}},
    "Outcome": {"rich_text": {}},
    "Callback": {"checkbox": {}},
    "Callback at": {"date": {}},
    # Dedupe helpers (not shown to Liam day-to-day, used by the Hunter):
    "Dedupe key": {"rich_text": {}},
    "Title+company hash": {"rich_text": {}},
}

FREELANCE_LEADS_SCHEMA: dict = {
    "Name": {"title": {}},
    "Type": _select("platform post", "Reddit", "HN", "local business"),
    "URL": {"url": {}},
    "Contact route": {"rich_text": {}},
    "What they need": {"rich_text": {}},
    "Budget": {"rich_text": {}},
    "Fit summary": {"rich_text": {}},
    "Pitch draft": {"rich_text": {}},
    "Status": _select("New", "Waiting for Liam", "Liam contacting", "Won", "Lost", "Skipped"),
}

SOURCES_SCHEMA: dict = {
    "Name": {"title": {}},
    "Type": _select("ATS", "board", "aggregator", "RSS", "VC board", "freelance"),
    "Endpoint": {"rich_text": {}},
    "Access": _select("API", "RSS", "HTML"),
    "Status": _select("proposed", "active", "paused", "broken"),
    "Last checked": {"date": {}},
    "Jobs found": {"number": {"format": "number"}},
    "Jobs approved": {"number": {"format": "number"}},
    "Callbacks": {"number": {"format": "number"}},
    "Notes on terms": {"rich_text": {}},
}

COMPANIES_SCHEMA: dict = {
    "Name": {"title": {}},
    "Careers URL": {"url": {}},
    "ATS": _select(*ATS_OPTIONS),
    "ATS slug": {"rich_text": {}},
    "Found via": {"rich_text": {}},
    "Last checked": {"date": {}},
    "Last new job at": {"date": {}},
    "Active": {"checkbox": {}},
}

# Lines Liam rejected, so the Writer never writes them again. Lives under Private
# (not the root page), and an entry is only added after Liam confirms it.
NEVER_AGAIN_SCHEMA: dict = {
    "Line": {"title": {}},
    "Reason": {"rich_text": {}},
    "Applies to": _select("shared", "cover letter", "CV"),
    "Date": {"date": {}},
    "Application": {"rich_text": {}},
}

# Order matters only for how they appear in the page.
DATABASES: dict[str, dict] = {
    "Jobs": JOBS_SCHEMA,
    "Freelance Leads": FREELANCE_LEADS_SCHEMA,
    "Sources": SOURCES_SCHEMA,
    "Companies": COMPANIES_SCHEMA,
}
