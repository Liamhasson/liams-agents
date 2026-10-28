"""Data models for Liam's agents.

These mirror the Notion databases described in docs/BUILD_BRIEF.md §6. The Job
model carries the dedupe logic, since de-duplication is the heart of Phase 1.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace for stable hashing."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Job:
    """A single job posting.

    Dedupe rule (BUILD_BRIEF §6): a job is the same if it shares
    (ats, company_slug, job_id) OR a hash of the normalised title + company.
    """

    title: str
    company: str
    url: str = ""
    apply_url: str = ""
    source: str = ""            # which Source found it, e.g. "Greenhouse", "Arbeitnow"
    ats: str = ""               # hiring tool, e.g. "greenhouse", "lever", "ashby"
    company_slug: str = ""      # the company's token/slug on that ATS
    job_id: str = ""            # the ATS's own id for this posting
    location: str = ""
    remote: str = ""            # "yes" | "no" | "hybrid"
    posted_at: str = ""         # ISO date
    first_seen_at: str = field(default_factory=_now_iso)
    role_type: str = ""
    description: str = ""       # captured during hunt; persisted later (Matcher phase)
    score: Optional[int] = None
    fit_summary: str = ""
    why_liam: str = ""
    gaps: str = ""
    flags: list[str] = field(default_factory=list)
    status: str = "New"
    apply_method: str = ""
    research_notes: str = ""
    cv_draft: str = ""
    cover_letter_draft: str = ""

    @property
    def title_company_hash(self) -> str:
        """Stable hash of normalised title + company. Secondary dedupe key."""
        basis = f"{_normalise(self.title)}|{_normalise(self.company)}"
        return hashlib.sha256(basis.encode()).hexdigest()[:16]

    @property
    def dedupe_key(self) -> str:
        """Primary dedupe key.

        Prefer the precise (ats, slug, id) triple when available; otherwise
        fall back to the title+company hash so boards without a stable id still
        de-duplicate.
        """
        if self.ats and self.company_slug and self.job_id:
            return f"{self.ats}:{self.company_slug}:{self.job_id}".lower()
        return f"hash:{self.title_company_hash}"


@dataclass
class FreelanceLead:
    name: str
    type: str = ""              # platform post | Reddit | HN | local business
    url: str = ""
    contact_route: str = ""
    what_they_need: str = ""
    budget: str = ""
    fit_summary: str = ""
    pitch_draft: str = ""
    status: str = "New"


@dataclass
class Source:
    name: str
    type: str = ""              # ATS | board | aggregator | RSS | VC board | freelance
    endpoint: str = ""
    access: str = ""            # API | RSS | HTML
    status: str = "proposed"    # proposed | active | paused | broken
    notes: str = ""


@dataclass
class Company:
    name: str
    careers_url: str = ""
    ats: str = ""
    ats_slug: str = ""
    found_via: str = ""
    active: bool = True
