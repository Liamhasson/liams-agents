"""Workable: GET apply.workable.com/api/v1/widget/accounts/{shortcode}?details=true"""

from __future__ import annotations

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote

ATS = "workable"


def fetch(client: PoliteClient, slug: str, company: str = "") -> list[Job]:
    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
    data = client.get(url).json()
    name = data.get("name") or company or slug
    jobs: list[Job] = []
    for j in data.get("jobs", []):
        loc_obj = j.get("location") or {}
        loc = ", ".join(x for x in [loc_obj.get("city"), loc_obj.get("country")] if x)
        remote = "yes" if loc_obj.get("telecommuting") else is_remote(loc, j.get("title", ""))
        link = j.get("application_url") or j.get("url") or ""
        jobs.append(Job(
            title=j.get("title", ""),
            company=name,
            url=link,
            apply_url=link,
            source=f"Workable:{slug}",
            ats=ATS,
            company_slug=slug,
            job_id=str(j.get("shortcode") or j.get("id") or ""),
            location=loc,
            remote=remote,
            posted_at=(j.get("created_at") or "")[:10],
            description=(j.get("description", "") or "")[:5000],
        ))
    return jobs
