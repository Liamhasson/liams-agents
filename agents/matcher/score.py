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
        "ghost_risk": {"type": "string", "enum": ["low", "medium", "high"],
                       "description": "Likelihood this is an evergreen/ghost post, from the text."},
        "ghost_reason": {"type": "string", "description": "One short phrase; '' if low."},
    },
    "required": ["score", "role_type", "fit_summary", "why_you", "gaps", "flags",
                 "german_required", "remote_eligibility", "ghost_risk", "ghost_reason"],
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
- ghost_risk: judge how likely this is an evergreen / "ghost" posting rather
  than a real, specific opening. HIGH signals: "we're always looking", "talent
  pool/community", "spontaneous/initiative application" ("Initiativbewerbung"),
  a generic blurb with no concrete team, responsibilities or project. MEDIUM:
  somewhat vague or boilerplate. LOW: a specific, concrete role. Put the tell in
  ghost_reason. This does NOT lower the score — it is a separate warning.
Return your answer by calling the submit_match tool."""


_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _to_dt(s: str):
    from datetime import datetime, timezone
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception:
            return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _to_date(s: str):
    dt = _to_dt(s)
    return dt.date() if dt else None


def freshness(posted_at: str, now_iso: str) -> str:
    """Priority tier by how recently the role was posted: fresh/recent/older.

    Uses the posting date (the signal that matters for 'apply first'). When the
    post date is unknown we return 'recent' (neutral) rather than guess 'fresh'.
    """
    posted, now = _to_dt(posted_at), _to_dt(now_iso)
    if not posted or not now:
        return "recent"
    hours = (now - posted).total_seconds() / 3600
    if hours <= 24:
        return "fresh"
    if hours <= 24 * 7:
        return "recent"
    return "older"


def assess_ghost(llm_risk: str, first_seen_at: str, posted_at: str, now_iso: str) -> tuple[str, list[str]]:
    """Merge the content-based ghost risk with behavioural signals (age/repost).

    Returns (risk, reasons). Behavioural signals strengthen over time as the
    Hunter keeps seeing the same posting.
    """
    risk = llm_risk if llm_risk in _RISK_ORDER else "low"
    reasons: list[str] = []

    def bump(level: str):
        nonlocal risk
        if _RISK_ORDER[level] > _RISK_ORDER[risk]:
            risk = level

    first, posted, now = _to_date(first_seen_at), _to_date(posted_at), _to_date(now_iso)
    # How long the role itself has been posted (noisy ATS dates -> high thresholds).
    if posted and now:
        pa = (now - posted).days
        if pa >= 180:
            bump("high"); reasons.append(f"posted ~{pa}d ago")
        elif pa >= 90:
            bump("medium"); reasons.append(f"posted ~{pa}d ago")
    # How long WE have been seeing it (accrues as the Hunter runs over time).
    if first and now:
        age = (now - first).days
        if age >= 180:
            bump("high"); reasons.append(f"seen for ~{age}d")
        elif age >= 90:
            bump("medium"); reasons.append(f"seen for ~{age}d")
    # Posting date refreshed well after we first saw it -> classic repost.
    if first and posted and (posted - first).days >= 14:
        bump("high"); reasons.append("posting date refreshed (likely reposted)")
    return risk, reasons


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
