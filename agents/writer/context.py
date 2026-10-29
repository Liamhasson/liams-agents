"""Load everything the Writer needs from Notion before drafting.

Facts come ONLY from Liam's mytone + base CV (both in Notion Private) and the
job's research notes — never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.notion import NotionClient
from shared.notion.client import plain_title, plain_text, plain_select, plain_url
from shared import config


@dataclass(frozen=True)
class NeverAgain:
    """A line Liam rejected. `applies_to` is "shared", "cover letter" or "CV"."""
    line: str
    reason: str
    applies_to: str = "shared"

    def applies(self, kind: str | None) -> bool:
        return kind is None or self.applies_to in ("shared", kind)


@dataclass(frozen=True)
class Reference:
    """A letter or CV Liam approved (Notion Private > Writer references)."""
    title: str
    kind: str  # "cover letter" or "CV"
    company: str
    role: str
    role_type: str
    approved: str  # ISO date
    text: str


_REF_META = {"Type": "kind", "Company": "company", "Role": "role",
             "Role type": "role_type", "Approved": "approved"}


def parse_reference(title: str, page_text: str) -> Reference:
    """Reference pages start with 'Key: value' lines (see learn.save_reference), then the text."""
    meta = {"kind": "cover letter", "company": "", "role": "", "role_type": "", "approved": ""}
    lines = page_text.splitlines()
    i = 0
    while i < len(lines) and lines[i].split(":", 1)[0] in _REF_META and ":" in lines[i]:
        key, value = lines[i].split(":", 1)
        meta[_REF_META[key]] = value.strip()
        i += 1
    body = lines[i:]
    text = "\n".join(body) if meta["kind"] == "CV" else "\n\n".join(body)
    return Reference(title=title, text=text, **meta)


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
    never_again: list[NeverAgain] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)


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
    """Load Liam's CV from Private — whether kept as sub-pages or uploaded .md files.

    If a CV is named "current", only that one is used: older versions carry stale
    titles and dates that would conflict with it.
    """
    import httpx
    private = _private_page_id(notion)
    if not private:
        return ""
    parts: list[tuple[str, str]] = []
    for b in notion._paginated("GET", f"/blocks/{private}/children?page_size=100"):
        t = b.get("type")
        if t == "child_page" and "cv" in b["child_page"].get("title", "").lower():
            parts.append((b["child_page"]["title"], notion.page_text(b["id"])))
        elif t == "file":
            url, name = _file_block_url_name(b)
            if url and (name.lower().endswith((".md", ".txt")) or "cv" in name.lower()):
                try:
                    parts.append((name, httpx.get(url, timeout=20, follow_redirects=True).text))
                except Exception:
                    pass
    current = [p for p in parts if "current" in p[0].lower()]
    return "\n\n---\n\n".join(text for _, text in (current or parts) if text.strip())


def load_mytone(notion: NotionClient) -> str:
    pid = notion.load_ids().get("mytone")
    if not pid:
        raise RuntimeError("mytone not set up. Run: python scripts/write_mytone.py")
    return notion.page_text(pid)


def load_never_again(notion: NotionClient) -> list[NeverAgain]:
    """Lines Liam rejected, from the "Never again" database under Private."""
    db = notion.load_ids().get("Never again")
    if not db:
        raise RuntimeError("Never again list not set up. Run: python scripts/setup_never_again.py")
    entries = [NeverAgain(plain_title(p), plain_text(p, "Reason"),
                          plain_select(p, "Applies to") or "shared")
               for p in notion.query_database(db)]
    return [e for e in entries if e.line.strip()]


def load_references(notion: NotionClient) -> list[Reference]:
    """Every approved letter and CV under Private > Writer references (empty if none yet)."""
    root = notion.load_ids().get("Writer references")
    if not root:
        return []
    return [parse_reference(b["child_page"]["title"], notion.page_text(b["id"]))
            for b in notion._paginated("GET", f"/blocks/{root}/children?page_size=100")
            if b.get("type") == "child_page"]


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
        never_again=load_never_again(notion),
        references=load_references(notion),
    )
