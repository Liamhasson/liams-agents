"""What a job post asks applicants to send.

The Matcher returns this in the call it already makes. Every item must carry the
post's own words, and code drops any item whose words aren't in the post.
"""

from __future__ import annotations

import re

from shared.quotes import appears_in

ASK_KINDS = ["cv", "cover_letter", "portfolio", "loom_or_video", "case_study",
             "form_questions", "linkedin", "other"]
ASK_STATES = ["required", "optional", "not_wanted"]

ASK_ITEM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ASK_KINDS},
        "state": {"type": "string", "enum": ASK_STATES},
        "quote": {"type": "string", "description": "The post's exact words that say this. Copy them, don't reword."},
    },
    "required": ["kind", "state", "quote"],
}

ASKS_RULES = """- application_asks: only what the post tells applicants to send or do in order to
  apply. Copy the post's exact words into quote. 'not_wanted' when the post says it
  doesn't want something (for example "no CVs"). If the post doesn't say, return an
  empty list. Never assume a CV or cover letter is wanted because most jobs want one.
  Only count what's needed to apply now. Later interview stages don't count."""

# Plain code, because on 25 real posts the model flagged "campaign graphics" as ads and
# missed "ad creative". Only words that clearly mean making ads count.
_AD_WORK = re.compile(
    r"\bad[- ](?:creatives?|campaigns?|designs?|production|work)\b"
    r"|advertising (?:campaign|creative|design|agency)"
    r"|paid (?:social|ads)\b|performance creative"
    r"|(?:design|create|produce|build)[^.\n]{0,30}\bads\b"
    r"|\bads\b[^.\n]{0,20}(?:creative|for (?:meta|google|tiktok|instagram|facebook|linkedin))",
    re.I)

_EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {"application_asks": {"type": "array", "items": ASK_ITEM_SCHEMA}},
    "required": ["application_asks"],
}


def verified_asks(raw: list[dict] | None, description: str) -> list[dict]:
    """Keep only the items whose quote is really in the post."""
    return [{"kind": a["kind"], "state": a["state"], "quote": a["quote"]}
            for a in (raw or []) if appears_in(a.get("quote", ""), description)]


def ad_work_line(description: str) -> str:
    """The post's own sentence about making ads, or '' if it doesn't mention any."""
    found = _AD_WORK.search(description or "")
    if not found:
        return ""
    start = max(description.rfind(c, 0, found.start()) for c in ".!?\n") + 1
    ends = [i for i in (description.find(c, found.end()) for c in ".!?\n") if i != -1]
    end = min(ends) + 1 if ends else len(description)
    return description[start:end].strip()[:200]


def extract_asks(claude, title: str, description: str) -> list[dict]:
    """For jobs scored before the Matcher read this."""
    system = "You read job posts and list what applicants are asked to send.\n" + ASKS_RULES
    res = claude.json_call(system, f"Title: {title}\n\nDescription:\n{description[:6000]}",
                           _EXTRACT_SCHEMA, tool_name="submit_asks", max_tokens=600)
    return verified_asks(res.get("application_asks"), description)
