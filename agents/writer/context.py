"""Load everything the Writer needs from Notion before drafting.

Facts come ONLY from Liam's mytone + base CV (both in Notion Private) and the
job's research notes — never invented.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_text, plain_select, plain_url
from shared import config


@dataclass
class WriterContext:
    job_page_id: str
    title: str
    company: str
    location: str
    role_type: str
    description: str
    research: str
    gaps: str
    url: str
    mytone: str
    base_cv: str


def _private_page_id(notion: NotionClient) -> str | None:
    root = config.require("NOTION_ROOT_PAGE_ID")
    for b in notion._paginated("GET", f"/blocks/{root}/children?page_size=100"):
        if b.get("type") == "child_page" and b["child_page"].get("title") == "Private":
            return b["id"]
    return None


def _file_block_url_name(block: dict) -> tuple[str, str]:
    fb = block.get("file", {})
    name = fb.get("name", "")
    if fb.get("type") == "external":
        return fb.get("external", {}).get("url", ""), name
    return fb.get("file", {}).get("url", ""), name


def load_base_cv(notion: NotionClient) -> str:
    """Load Liam's CV(s) from Private — whether kept as sub-pages or uploaded .md files."""
    import httpx
    private = _private_page_id(notion)
    if not private:
        return ""
    parts = []
    for b in notion._paginated("GET", f"/blocks/{private}/children?page_size=100"):
        t = b.get("type")
        if t == "child_page" and "cv" in b["child_page"].get("title", "").lower():
            parts.append(notion.page_text(b["id"]))
        elif t == "file":
            url, name = _file_block_url_name(b)
            if url and (name.lower().endswith((".md", ".txt")) or "cv" in name.lower()):
                try:
                    parts.append(httpx.get(url, timeout=20, follow_redirects=True).text)
                except Exception:
                    pass
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def load_mytone(notion: NotionClient) -> str:
    pid = notion.load_ids().get("mytone")
    if not pid:
        raise RuntimeError("mytone not set up. Run: python scripts/write_mytone.py")
    return notion.page_text(pid)


def build_context(notion: NotionClient, job_page: dict) -> WriterContext:
    return WriterContext(
        job_page_id=job_page["id"],
        title=plain_title(job_page),
        company=plain_text(job_page, "Company"),
        location=plain_text(job_page, "Location"),
        role_type=plain_select(job_page, "Role type"),
        description=plain_text(job_page, "Description"),
        research=plain_text(job_page, "Research notes"),
        gaps=plain_text(job_page, "Gaps"),
        url=plain_url(job_page, "URL") or plain_url(job_page, "Apply URL"),
        mytone=load_mytone(notion),
        base_cv=load_base_cv(notion),
    )
