"""What a job post asks applicants to send.

The Matcher returns this in the call it already makes. Every item must carry the
post's own words, and code drops any item whose words aren't in the post.
"""

from __future__ import annotations

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
- ad_work_quote: if making ads (ad campaigns, ad creative, paid social) is part of
  the role, copy the post's exact words. Otherwise ''."""

_EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {"application_asks": {"type": "array", "items": ASK_ITEM_SCHEMA}},
    "required": ["application_asks"],
}


def verified_asks(raw: list[dict] | None, description: str) -> list[dict]:
    """Keep only the items whose quote is really in the post."""
    return [{"kind": a["kind"], "state": a["state"], "quote": a["quote"]}
            for a in (raw or []) if appears_in(a.get("quote", ""), description)]


def extract_asks(claude, title: str, description: str) -> list[dict]:
    """For jobs scored before the Matcher read this."""
    system = "You read job posts and list what applicants are asked to send.\n" + ASKS_RULES
    res = claude.json_call(system, f"Title: {title}\n\nDescription:\n{description[:6000]}",
                           _EXTRACT_SCHEMA, tool_name="submit_asks", max_tokens=600)
    return verified_asks(res.get("application_asks"), description)
