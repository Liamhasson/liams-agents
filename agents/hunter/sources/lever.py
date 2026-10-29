"""Lever: GET api.lever.co/v0/postings/{site}?mode=json (EU: api.eu.lever.co)"""

from __future__ import annotations

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote

ATS = "lever"


def fetch(client: PoliteClient, slug: str, company: str = "") -> list[Job]:
    jobs: list[Job] = []
    for host in ("api.lever.co", "api.eu.lever.co"):
        url = f"https://{host}/v0/postings/{slug}?mode=json"
        try:
            data = client.get(url).json()
        except Exception:
            continue
        for j in data:
            cats = j.get("categories") or {}
            loc = cats.get("location", "") or ""
            jobs.append(Job(
                title=j.get("text", ""),
                company=company or slug,
                url=j.get("hostedUrl", ""),
                apply_url=j.get("applyUrl", "") or j.get("hostedUrl", ""),
                source=f"Lever:{slug}",
                ats=ATS,
                company_slug=slug,
                job_id=str(j.get("id", "")),
                location=loc,
                remote=is_remote(loc, cats.get("commitment", ""), j.get("text", "")),
                description=(j.get("descriptionPlain", "") or "")[:6000],
            ))
        if jobs:
            break  # found the right region
    return jobs
