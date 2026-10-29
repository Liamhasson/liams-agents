"""Generic RSS adapter for job feeds (Berlin Startup Jobs, Dribbble, WWR...).

Company name rarely has its own field in RSS, so we extract it from the title
using a per-feed `style`:
  - "at":    "Role at Company"      -> company after the last ' at '
  - "colon": "Company: Role"        -> company before the first ': '
  - "dash":  "Role - Company"       -> company after the last ' - '/' – '
  - None:    unknown -> fall back to the source name
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from shared.http import PoliteClient
from shared.models import Job
from . import is_remote


def _split_company(title: str, style: str | None, fallback: str) -> tuple[str, str]:
    t = title.strip()
    if style == "at" and " at " in t:
        role, company = t.rsplit(" at ", 1)
        return role.strip(), company.strip()
    if style == "colon" and ": " in t:
        company, role = t.split(": ", 1)
        return role.strip(), company.strip()
    if style == "dash":
        for sep in (" – ", " — ", " - "):
            if sep in t:
                role, company = t.rsplit(sep, 1)
                return role.strip(), company.strip()
    return t, fallback


def _tag(el, name: str) -> str:
    for child in el:
        if child.tag.split("}")[-1] == name and child.text:
            return child.text.strip()
    return ""


def fetch(client: PoliteClient, endpoint: str, source_name: str = "",
          style: str | None = None, attribution: str = "") -> list[Job]:
    xml = client.get(endpoint).text
    root = ET.fromstring(xml)
    jobs: list[Job] = []
    for item in root.iter("item"):
        raw_title = _tag(item, "title")
        link = _tag(item, "link")
        desc = re.sub(r"<[^>]+>", " ", _tag(item, "description"))
        pub = _tag(item, "pubDate")
        title, company = _split_company(raw_title, style, source_name)
        src = f"{source_name} — {attribution}" if attribution else source_name
        jobs.append(Job(
            title=title,
            company=company,
            url=link,
            apply_url=link,
            source=src,
            job_id=(_tag(item, "guid") or link)[:120],
            location="Remote" if is_remote(raw_title, desc) else "",
            remote=is_remote(raw_title, desc),
            posted_at=pub,
            description=desc.strip()[:6000],
        ))
    return jobs
