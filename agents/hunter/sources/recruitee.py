"""Recruitee: GET {co}.recruitee.com/api/offers/"""

from __future__ import annotations

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote

ATS = "recruitee"


def fetch(client: PoliteClient, slug: str, company: str = "") -> list[Job]:
    url = f"https://{slug}.recruitee.com/api/offers/"
    data = client.get(url).json()
    jobs: list[Job] = []
    for j in data.get("offers", []):
        loc = ", ".join(x for x in [j.get("city"), j.get("country")] if x) or j.get("location", "")
        remote = "yes" if j.get("remote") else is_remote(loc, j.get("title", ""))
        link = j.get("careers_url", "") or j.get("url", "")
        jobs.append(Job(
            title=j.get("title", ""),
            company=company or slug,
            url=link,
            apply_url=j.get("careers_apply_url", "") or link,
            source=f"Recruitee:{slug}",
            ats=ATS,
            company_slug=slug,
            job_id=str(j.get("id", "")),
            location=loc,
            remote=remote,
            posted_at=(j.get("published_at") or j.get("created_at") or "")[:10],
            description=(j.get("description", "") or "")[:5000],
        ))
    return jobs
