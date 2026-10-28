"""Maps Notion rows to source adapters.

- ATS_ADAPTERS: a Company's "ATS" value -> that ATS's fetch(client, slug, company).
- FEEDS: a Source's "Name" -> how to fetch that feed. The seed script creates
  matching Source rows so Liam can pause/activate each one from Notion.
"""

from __future__ import annotations

from .sources import greenhouse, lever, ashby, personio, workable, recruitee
from .sources import rss, arbeitnow, remotive, remoteok

ATS_ADAPTERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "personio": personio.fetch,
    "workable": workable.fetch,
    "recruitee": recruitee.fetch,
}

FEEDS: dict[str, dict] = {
    "Berlin Startup Jobs — Design/UX": {
        "fetch": rss.fetch,
        "endpoint": "https://berlinstartupjobs.com/design-ux/feed/",
        "type": "RSS", "access": "RSS",
        "kwargs": {"style": "dash"},
        "notes": "Berlin startup design/UX roles.",
    },
    "Dribbble Jobs": {
        "fetch": rss.fetch,
        "endpoint": "https://dribbble.com/jobs.rss",
        "type": "RSS", "access": "RSS",
        "kwargs": {"style": "at"},
        "notes": "Design jobs from Dribbble.",
    },
    "We Work Remotely — Design": {
        "fetch": rss.fetch,
        "endpoint": "https://weworkremotely.com/categories/remote-design-jobs.rss",
        "type": "RSS", "access": "RSS",
        "kwargs": {"style": "colon"},
        "notes": "Remote design roles.",
    },
    "Arbeitnow": {
        "fetch": arbeitnow.fetch,
        "endpoint": "https://www.arbeitnow.com/api/job-board-api",
        "type": "aggregator", "access": "API",
        "kwargs": {},
        "notes": "Free API, DE startups, founder-associate roles appear here.",
    },
    "Remotive — Design": {
        "fetch": remotive.fetch,
        "endpoint": "https://remotive.com/api/remote-jobs?category=design",
        "type": "aggregator", "access": "API",
        "kwargs": {},
        "notes": "Attribution required; stored on each job.",
    },
    "RemoteOK": {
        "fetch": remoteok.fetch,
        "endpoint": "https://remoteok.com/api",
        "type": "aggregator", "access": "API",
        "kwargs": {},
        "notes": "Attribution required; stored on each job.",
    },
}
