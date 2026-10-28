"""Source adapters. Each ATS adapter exposes:

    fetch(client, slug, company="") -> list[Job]

and each feed adapter exposes:

    fetch(client, endpoint, source_name="") -> list[Job]
"""

from __future__ import annotations


def is_remote(*texts: str) -> str:
    """Return 'yes' if any text signals remote, else '' (unknown)."""
    blob = " ".join(t or "" for t in texts).lower()
    return "yes" if "remote" in blob else ""
