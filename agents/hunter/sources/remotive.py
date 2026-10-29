"""Remotive: GET https://remotive.com/api/remote-jobs?category=design

Attribution required by Remotive's terms — stored on each job's source label.
"""

from __future__ import annotations

import re

from shared.http import PoliteClient
from shared.models import Job

ATTRIBUTION = "Jobs by Remotive (https://remotive.com/remote-jobs)"


def fetch(client: PoliteClient, endpoint: str = "https://remotive.com/api/remote-jobs?category=design",
          source_name: str = "Remotive", **_) -> list[Job]:
    data = client.get(endpoint).json()
    jobs: list[Job] = []
    for j in data.get("jobs", []):
        desc = re.sub(r"<[^>]+>", " ", j.get("description", "") or "")
        jobs.append(Job(
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            url=j.get("url", ""),
            apply_url=j.get("url", ""),
            source=f"{source_name} — {ATTRIBUTION}",
            job_id=str(j.get("id", "")),
            location=j.get("candidate_required_location", "") or "",
            remote="yes",
            posted_at=(j.get("publication_date") or "")[:10],
            description=desc.strip()[:6000],
        ))
    return jobs
