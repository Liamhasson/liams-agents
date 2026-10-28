"""Score a single job against Liam's profile using Haiku with strict JSON."""

from __future__ import annotations

from shared.claude import Claude
from shared.notion.schema import ROLE_TYPES, JOB_FLAGS

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100,
                  "description": "0-100 fit for Liam. Be decisive, use the full range."},
        "role_type": {"type": "string", "enum": ROLE_TYPES},
        "fit_summary": {"type": "string", "description": "1-2 lines: what the role is."},
        "why_you": {"type": "string", "description": "2 lines tying it to Liam's real work; no invention."},
        "gaps": {"type": "string", "description": "Honest gaps, e.g. 'asks for 5+ yrs'. '' if none."},
        "flags": {"type": "array", "items": {"type": "string", "enum": JOB_FLAGS}},
        "german_required": {"type": "string", "enum": ["none", "basic", "fluent"]},
        "remote_eligibility": {"type": "string", "enum": ["berlin", "remote_de_ok", "unclear", "no"]},
    },
    "required": ["score", "role_type", "fit_summary", "why_you", "gaps",
                 "flags", "german_required", "remote_eligibility"],
}

SYSTEM = """You score design jobs for Liam Hasson against his profile below.
Be a sharp, honest filter — not a cheerleader. Use the full 0-100 range.

=== LIAM'S PROFILE ===
{profile}
=== END PROFILE ===

Scoring guidance:
- 70-100: clearly fits his role types AND level AND location AND language.
- 40-69: adjacent or partial mismatch (seniority gap, unclear remote eligibility,
  only loosely a design role) — worth asking Liam about.
- 0-39: wrong field, senior-only (5+ yrs product design / Lead / Principal),
  requires fluent German, or not hirable in Germany.

Rules:
- german_required: 'fluent' if the post needs business/fluent German or
  "Deutsch fließend / verhandlungssicher"; 'basic' if nice-to-have; else 'none'.
- remote_eligibility: 'berlin' if Berlin-based; 'remote_de_ok' if remote and can
  employ someone living in Germany/EU; 'no' if it excludes Germany or needs
  relocation elsewhere; 'unclear' if you truly can't tell.
- flags: add 'senior' for senior/lead/principal; 'experience gap' if it asks for
  more product-design years than Liam has; 'contract'/'unpaid' where stated.
- why_you and gaps must be grounded only in Liam's real experience. Never invent.
- Working-student roles are not wanted; score them low.
Return your answer by calling the submit_match tool."""


def is_hard_drop(title: str, description: str, keywords: list[str]) -> bool:
    blob = f"{title} {description}".lower()
    return any(k.lower() in blob for k in keywords)


def route(result: dict, alert: int, ask: int) -> tuple[str, str]:
    """Map a scored result to a decision: 'alert' | 'ask' | 'dropped', plus a reason."""
    if result.get("german_required") == "fluent":
        return "dropped", "requires fluent German"
    if result.get("remote_eligibility") == "no":
        return "dropped", "not Berlin / not hirable in Germany"
    sc = int(result["score"])
    if sc < ask:
        return "dropped", f"low score ({sc})"
    if sc < alert:
        return "ask", ""
    return "alert", ""


def score(claude: Claude, profile: str, *, title: str, company: str,
          location: str, remote: str, description: str) -> dict:
    user = (
        f"Title: {title}\n"
        f"Company: {company}\n"
        f"Location: {location or 'unknown'}\n"
        f"Remote: {remote or 'unknown'}\n\n"
        f"Description:\n{(description or '(no description captured)')[:6000]}"
    )
    return claude.json_call(
        system=SYSTEM.format(profile=profile),
        user=user,
        schema=SCHEMA,
        tool_name="submit_match",
        max_tokens=800,
    )
