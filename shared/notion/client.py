"""A thin, dependency-light Notion API client.

Built on httpx (already a project dependency) rather than a heavier SDK. It
covers exactly what the agents need: create/reuse the databases, write and read
job rows, and the dedupe query. Rate-limited and retried on 429 per Notion's
limits (~3 requests/second).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from .. import config
from ..models import Job
from .schema import DATABASES

NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"
_IDS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "notion_ids.json"

# Notion rich_text accepts at most 2000 chars per text object. Some characters
# (emoji / non-BMP) count as 2 on Notion's side, so we keep headroom.
_MAX_TEXT = 1900


def _rt(s: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": (s or "")[:_MAX_TEXT]}}]}


def _title(s: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": (s or "")[:_MAX_TEXT]}}]}


def _coerce_date(s: str) -> Optional[str]:
    """Return an ISO-8601 date/datetime Notion will accept, or None.

    Handles ISO strings (as-is) and RFC-822 feed dates ('Mon, 26 Oct 2026 ...').
    """
    if not s:
        return None
    s = s.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s).isoformat()
    except Exception:
        return None


class NotionClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or config.require("NOTION_TOKEN")
        self._http = httpx.Client(
            timeout=30,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )

    # ---- low-level ------------------------------------------------------
    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        url = f"{API}{path}"
        for attempt in range(5):
            r = self._http.request(method, url, json=payload)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", "1"))
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Notion {method} {path} → {r.status_code}: {r.text[:400]}")
            # gentle pacing to stay under ~3 req/s
            time.sleep(0.34)
            return r.json()
        raise RuntimeError(f"Notion {method} {path} kept returning 429 after retries")

    def _paginated(self, method: str, path: str, payload: Optional[dict] = None) -> list[dict]:
        # Notion wants pagination as a query param on GET, but in the body on POST.
        results: list[dict] = []
        cursor: Optional[str] = None
        while True:
            if method.upper() == "GET":
                sep = "&" if "?" in path else "?"
                url = path + (f"{sep}start_cursor={cursor}" if cursor else "")
                data = self._request("GET", url, None)
            else:
                body = dict(payload or {})
                if cursor:
                    body["start_cursor"] = cursor
                data = self._request("POST", path, body)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                return results
            cursor = data["next_cursor"]

    # ---- databases ------------------------------------------------------
    def find_databases_under(self, page_id: str) -> dict[str, str]:
        """Return {database_title: database_id} for inline databases on a page."""
        blocks = self._paginated("GET", f"/blocks/{page_id}/children?page_size=100")
        found: dict[str, str] = {}
        for b in blocks:
            if b.get("type") == "child_database":
                title = b["child_database"].get("title", "")
                if title:
                    found[title] = b["id"]
        return found

    def create_database(self, parent_page_id: str, title: str, properties: dict) -> str:
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "is_inline": True,
            "properties": properties,
        }
        return self._request("POST", "/databases", payload)["id"]

    def ensure_databases(self, root_page_id: Optional[str] = None) -> dict[str, str]:
        """Create the four databases under the root page, reusing any that exist.

        Idempotent: safe to run repeatedly. Writes the resulting ids to
        config/notion_ids.json so other code can look them up cheaply.
        """
        root = root_page_id or config.require("NOTION_ROOT_PAGE_ID")
        existing = self.find_databases_under(root)
        ids: dict[str, str] = {}
        for name, schema in DATABASES.items():
            if name in existing:
                ids[name] = existing[name]
                self._add_missing_properties(existing[name], schema)
            else:
                ids[name] = self.create_database(root, name, schema)
        merged = {**self.load_ids(), **ids}  # preserve non-database ids (e.g. the profile page)
        _IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _IDS_PATH.write_text(json.dumps(merged, indent=2) + "\n")
        return merged

    def _add_missing_properties(self, db_id: str, schema: dict) -> None:
        """Add any schema properties not yet on an existing database (migration)."""
        current = self._request("GET", f"/databases/{db_id}").get("properties", {})
        missing = {k: v for k, v in schema.items() if k not in current}
        if missing:
            self._request("PATCH", f"/databases/{db_id}", {"properties": missing})

    @staticmethod
    def load_ids() -> dict[str, str]:
        if _IDS_PATH.exists():
            return json.loads(_IDS_PATH.read_text())
        return {}

    def save_id(self, key: str, value: str) -> None:
        ids = self.load_ids()
        ids[key] = value
        _IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _IDS_PATH.write_text(json.dumps(ids, indent=2) + "\n")

    def query_database(self, db_id: str, filter: Optional[dict] = None) -> list[dict]:
        payload = {"filter": filter} if filter else {}
        return self._paginated("POST", f"/databases/{db_id}/query", payload)

    # ---- pages ----------------------------------------------------------
    def create_page(self, db_id: str, properties: dict) -> dict:
        return self._request("POST", "/pages", {"parent": {"database_id": db_id}, "properties": properties})

    def get_page(self, page_id: str) -> dict:
        return self._request("GET", f"/pages/{page_id}")

    def page_text(self, page_id: str) -> str:
        """Concatenate the visible text of a page's blocks (for loading docs)."""
        blocks = self._paginated("GET", f"/blocks/{page_id}/children?page_size=100")
        lines: list[str] = []
        for b in blocks:
            btype = b.get("type", "")
            body = b.get(btype, {})
            rt = body.get("rich_text", []) if isinstance(body, dict) else []
            text = "".join(x.get("plain_text", "") for x in rt)
            if text.strip():
                lines.append(text)
        return "\n".join(lines)

    def update_page(self, page_id: str, properties: dict) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def archive_page(self, page_id: str) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", {"archived": True})

    # ---- jobs -----------------------------------------------------------
    @staticmethod
    def job_to_properties(job: Job) -> dict:
        props: dict[str, Any] = {
            "Title": _title(job.title),
            "Company": _rt(job.company),
            "Source": _rt(job.source),
            "Location": _rt(job.location),
            "First seen at": {"date": {"start": job.first_seen_at}},
            "Last seen at": {"date": {"start": job.first_seen_at}},
            "Times seen": {"number": 1},
            "Status": {"select": {"name": job.status or "New"}},
            "Dedupe key": _rt(job.dedupe_key),
            "Title+company hash": _rt(job.title_company_hash),
        }
        if job.url:
            props["URL"] = {"url": job.url}
        if job.apply_url:
            props["Apply URL"] = {"url": job.apply_url}
        if job.ats:
            props["Company ATS"] = {"select": {"name": job.ats}}
        if job.remote:
            props["Remote"] = {"select": {"name": job.remote}}
        _posted = _coerce_date(job.posted_at)
        if _posted:
            props["Posted at"] = {"date": {"start": _posted}}
        if job.role_type:
            props["Role type"] = {"select": {"name": job.role_type}}
        if job.description:
            props["Description"] = _rt(job.description)
        if job.score is not None:
            props["Score"] = {"number": job.score}
        if job.fit_summary:
            props["Fit summary"] = _rt(job.fit_summary)
        if job.why_liam:
            props["Why Liam"] = _rt(job.why_liam)
        if job.gaps:
            props["Gaps"] = _rt(job.gaps)
        if job.flags:
            props["Flags"] = {"multi_select": [{"name": f} for f in job.flags]}
        if job.apply_method:
            props["Apply method"] = {"select": {"name": job.apply_method}}
        return props

    def find_job(self, jobs_db_id: str, job: Job) -> Optional[dict]:
        """Return the existing Notion page for this job, or None. Dedupe per §6."""
        filter = {
            "or": [
                {"property": "Dedupe key", "rich_text": {"equals": job.dedupe_key}},
                {"property": "Title+company hash", "rich_text": {"equals": job.title_company_hash}},
            ]
        }
        matches = self.query_database(jobs_db_id, filter)
        return matches[0] if matches else None

    def upsert_job(self, jobs_db_id: str, job: Job) -> tuple[dict, bool]:
        """Create the job if new; otherwise return the existing row.

        Returns (page, created). On a duplicate we keep the earliest row and do
        NOT overwrite it, preserving the original "First seen at".
        """
        existing = self.find_job(jobs_db_id, job)
        if existing:
            # Track that we saw it again (repost/age signal) and backfill a
            # missing description — without touching First seen / Status / Score.
            seen = (plain_number(existing, "Times seen") or 1) + 1
            update: dict = {
                "Times seen": {"number": seen},
                "Last seen at": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
            }
            if job.description and not plain_text(existing, "Description"):
                update["Description"] = _rt(job.description)
            self.update_page(existing["id"], update)
            return existing, False
        return self.create_page(jobs_db_id, self.job_to_properties(job)), True


# ---- small read helpers (handy for demos / tests) -----------------------
def plain_title(page: dict) -> str:
    for v in page.get("properties", {}).values():
        if v.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in v.get("title", []))
    return ""


def plain_text(page: dict, prop: str) -> str:
    v = page.get("properties", {}).get(prop, {})
    if v.get("type") == "rich_text":
        return "".join(t.get("plain_text", "") for t in v.get("rich_text", []))
    return ""


def plain_select(page: dict, prop: str) -> str:
    v = page.get("properties", {}).get(prop, {})
    sel = v.get("select")
    return sel.get("name", "") if sel else ""


def plain_number(page: dict, prop: str):
    return page.get("properties", {}).get(prop, {}).get("number")


def plain_date(page: dict, prop: str) -> str:
    d = page.get("properties", {}).get(prop, {}).get("date")
    return d.get("start", "") if d else ""


def plain_url(page: dict, prop: str) -> str:
    return page.get("properties", {}).get(prop, {}).get("url") or ""


def plain_checkbox(page: dict, prop: str) -> bool:
    return bool(page.get("properties", {}).get(prop, {}).get("checkbox"))
