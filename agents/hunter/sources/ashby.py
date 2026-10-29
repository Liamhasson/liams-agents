"""Ashby: GET api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true"""

from __future__ import annotations

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote

ATS = "ashby"


def fetch(client: PoliteClient, slug: str, company: str = "") -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    data = client.get(url).json()
    jobs: list[Job] = []
    for j in data.get("jobs", []):
        loc = j.get("location", "") or ""
        remote = "yes" if j.get("isRemote") else is_remote(loc, j.get("title", ""))
        jobs.append(Job(
            title=j.get("title", ""),
            company=company or slug,
            url=j.get("jobUrl", ""),
            apply_url=j.get("applyUrl", "") or j.get("jobUrl", ""),
            source=f"Ashby:{slug}",
            ats=ATS,
            company_slug=slug,
            job_id=str(j.get("id", "")),
            location=loc,
            remote=remote,
            posted_at=(j.get("publishedAt") or j.get("publishedDate") or "")[:10],
            description=(j.get("descriptionPlain", "") or "")[:6000],
        ))
    return jobs
