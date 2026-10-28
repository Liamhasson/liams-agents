"""The Hunter's permissive title gate.

This is NOT the Matcher. It only drops titles that are obviously not design, to
keep the Jobs database tidy. When in doubt it keeps the job.
"""

from __future__ import annotations


def title_passes(title: str, cfg: dict) -> bool:
    t = (title or "").lower()
    if not t:
        return False
    # Force-keep known design-adjacent exceptions (e.g. "design engineer").
    for exc in cfg.get("title_exclude_exceptions", []):
        if exc.lower() in t:
            return True
    # Drop obvious non-design roles.
    for bad in cfg.get("title_exclude", []):
        if bad.lower() in t:
            return False
    # Keep anything matching a design keyword.
    for kw in cfg.get("title_keywords", []):
        if kw.lower() in t:
            return True
    return False
