"""Read an application form where the hiring tool publishes it.

Only Greenhouse does (`questions=true` on its public job board API). Ashby's
robots.txt disallows the path its form loads from, so other tools are left alone
and the Director asks Liam to paste the questions.
"""

from __future__ import annotations

import re
from typing import Optional

_IDENTITY = {"first name", "last name", "preferred name", "email", "phone"}


def parse_greenhouse(source: str, url: str) -> Optional[tuple[str, str]]:
    """(board, job id) for a Greenhouse job, else None."""
    board = re.match(r"greenhouse:([\w-]+)", source or "", re.I)
    job = re.search(r"(?:gh_jid=|/jobs/)(\d+)", url or "")
    return (board.group(1), job.group(1)) if board and job else None


def _clean(label: str) -> str:
    """Some forms put a line of underscores above a question as a divider."""
    return re.sub(r"_{3,}", " ", label or "").strip()


def greenhouse_questions(client, slug: str, job_id: str) -> Optional[list[dict]]:
    """The form's questions without name, email and phone. None if it can't be read."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?questions=true"
    try:
        data = client.get(url).json()
    except Exception:  # a closed post is a 404
        return None
    out = []
    for q in data.get("questions") or []:
        label = _clean(q.get("label", ""))
        if label and label.lower() not in _IDENTITY:
            fields = q.get("fields") or [{}]
            out.append({"label": label, "required": bool(q.get("required")), "type": fields[0].get("type", "")})
    return out
