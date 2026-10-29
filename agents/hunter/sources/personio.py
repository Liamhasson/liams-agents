"""Personio: GET {sub}.jobs.personio.de/xml?language=en  (XML feed)"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote

ATS = "personio"


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def fetch(client: PoliteClient, slug: str, company: str = "") -> list[Job]:
    url = f"https://{slug}.jobs.personio.de/xml?language=en"
    xml = client.get(url).text
    root = ET.fromstring(xml)
    jobs: list[Job] = []
    for pos in root.iter("position"):
        job_id = _text(pos, "id")
        title = _text(pos, "name")
        office = _text(pos, "office")
        # description lives in jobDescriptions/jobDescription/value
        desc_parts = [el.text or "" for el in pos.iter("value")]
        desc = " ".join(p.strip() for p in desc_parts if p)
        jobs.append(Job(
            title=title,
            company=company or slug,
            url=f"https://{slug}.jobs.personio.de/job/{job_id}",
            apply_url=f"https://{slug}.jobs.personio.de/job/{job_id}",
            source=f"Personio:{slug}",
            ats=ATS,
            company_slug=slug,
            job_id=job_id,
            location=office,
            remote=is_remote(office, _text(pos, "schedule"), title),
            posted_at=(_text(pos, "createdAt") or "")[:10],
            description=desc[:6000],
        ))
    return jobs
