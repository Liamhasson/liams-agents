"""RemoteOK: GET https://remoteok.com/api  (first element is legal/attribution).

Attribution required by RemoteOK's terms — stored on each job's source label.
"""

from __future__ import annotations

import re

from shared.http import PoliteClient
from shared.models import Job

ATTRIBUTION = "Data by RemoteOK (https://remoteok.com)"


def fetch(client: PoliteClient, endpoint: str = "https://remoteok.com/api",
          source_name: str = "RemoteOK", **_) -> list[Job]:
    data = client.get(endpoint).json()
    jobs: list[Job] = []
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue  # skips the leading legal/attribution notice object
        desc = re.sub(r"<[^>]+>", " ", j.get("description", "") or "")
        jobs.append(Job(
            title=j.get("position", ""),
            company=j.get("company", ""),
            url=j.get("url", ""),
            apply_url=j.get("apply_url", "") or j.get("url", ""),
            source=f"{source_name} — {ATTRIBUTION}",
            job_id=str(j.get("id", "")),
            location=j.get("location", "") or "Remote",
            remote="yes",
            posted_at=(j.get("date") or "")[:10],
            description=desc.strip()[:6000],
        ))
    return jobs
