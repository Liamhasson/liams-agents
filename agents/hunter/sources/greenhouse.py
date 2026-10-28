"""Greenhouse: GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""

from __future__ import annotations

import re

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote

ATS = "greenhouse"


def fetch(client: PoliteClient, slug: str, company: str = "") -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    data = client.get(url).json()
    jobs: list[Job] = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        content = re.sub(r"<[^>]+>", " ", j.get("content", "") or "")
        jobs.append(Job(
            title=j.get("title", ""),
            company=company or slug,
            url=j.get("absolute_url", ""),
            apply_url=j.get("absolute_url", ""),
            source=f"Greenhouse:{slug}",
            ats=ATS,
            company_slug=slug,
            job_id=str(j.get("id", "")),
            location=loc,
            remote=is_remote(loc, j.get("title", "")),
            posted_at=(j.get("updated_at") or "")[:10],
            description=content.strip()[:5000],
        ))
    return jobs
