"""Arbeitnow: GET https://www.arbeitnow.com/api/job-board-api (free, DE startups)."""

from __future__ import annotations

import re

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote


def fetch(client: PoliteClient, endpoint: str = "https://www.arbeitnow.com/api/job-board-api",
          source_name: str = "Arbeitnow", **_) -> list[Job]:
    data = client.get(endpoint).json()
    jobs: list[Job] = []
    for j in data.get("data", []):
        loc = j.get("location", "") or ""
        remote = "yes" if j.get("remote") else is_remote(loc, j.get("title", ""))
        desc = re.sub(r"<[^>]+>", " ", j.get("description", "") or "")
        jobs.append(Job(
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            url=j.get("url", ""),
            apply_url=j.get("url", ""),
            source=source_name,
            job_id=str(j.get("slug", ""))[:120],
            location=loc,
            remote=remote,
            description=desc.strip()[:5000],
        ))
    return jobs
