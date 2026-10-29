"""Score a single job against Liam's profile using Haiku with strict JSON."""

from __future__ import annotations

import re

from shared.claude import Claude
from shared.notion.schema import ROLE_TYPES, JOB_FLAGS, FIELDS

DISCIPLINES = ["product", "brand", "graphic/visual"]

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
        "years_required": {"type": "integer", "minimum": 0, "maximum": 30,
                           "description": "Minimum years of design experience asked. 0 if none stated."},
        "discipline": {"type": "string", "enum": DISCIPLINES,
                       "description": "Which kind of design experience the post asks for."},
        "field": {"type": "string", "enum": FIELDS,
                  "description": "What the COMPANY works in (not the role)."},
        "german_required": {"type": "string", "enum": ["none", "basic", "fluent"]},
        "remote_eligibility": {"type": "string", "enum": ["berlin", "remote_de_ok", "unclear", "no"]},
        "ghost_risk": {"type": "string", "enum": ["low", "medium", "high"],
                       "description": "Likelihood this is an evergreen/ghost post, from the text."},
        "ghost_reason": {"type": "string", "description": "One short phrase; '' if low."},
    },
    "required": ["score", "role_type", "field", "fit_summary", "why_you", "gaps", "flags",
                 "years_required", "discipline", "german_required", "remote_eligibility", "ghost_risk", "ghost_reason"],
}

SYSTEM = """You score design jobs for Liam Hasson against his profile below.
Be a sharp, honest filter — not a cheerleader. Use the full 0-100 range.

=== LIAM'S PROFILE ===
{profile}
=== END PROFILE ===

Scoring guidance:
- 70-100: clearly fits his role types AND level AND location AND language.
- 40-69: adjacent or partial mismatch (unclear remote eligibility, only loosely
  a design role) — worth asking Liam about.
- 0-39: wrong field, requires German, or not hirable in Germany.
- Score the fit only. Don't add points for Berlin or the company's field, and
  don't take points off for the years of experience asked: those adjustments are
  made afterwards from years_required.

Rules:
- german_required: 'fluent' whenever German is REQUIRED at any level (e.g.
  "gute Deutschkenntnisse", "German B1/B2/C1", "Deutsch fließend /
  verhandlungssicher", "German is a must") or the post itself is written in
  German. 'basic' only if German is explicitly a plus / nice-to-have. Else 'none'.
- remote_eligibility: 'berlin' if the role is in Berlin (office or hybrid);
  'remote_de_ok' if fully remote and can employ someone living in Germany/EU;
  'no' if it is on-site or hybrid in any city other than Berlin (London, Paris,
  Munich, ...), excludes Germany, or needs relocation; 'unclear' only when the
  post gives no location at all.
- field: what the company works in. 'rock/live music' for rock or live music
  (concerts, venues, festivals, touring, ticketing, rock labels/media); 'music'
  for any other music company (labels like UMG, streaming, instruments and gear,
  music apps, music tech); 'sport'; 'travel'; 'nature' (outdoors, climate,
  environment); 'animals' (pets, vets, wildlife); 'innovative tech' only when the
  product itself is new technology (AI models or agents, robotics, space, new
  hardware, deep tech); 'cyber' (cybersecurity, defence tech). Software tools,
  productivity, finance, B2B SaaS and marketplaces are 'other', even if they use AI.
- years_required: the minimum years of design experience (product, UX, UI,
  visual, brand) the post asks for, as a number. "5+ years" -> 5; "3-5 years" -> 3;
  "at least 4 years" -> 4. 0 if the post states no number, even for a senior title.
- discipline: 'product' for product, UX/UI, interaction, web and growth design
  and design engineering; 'brand' for brand design and brand identity;
  'graphic/visual' for graphic, visual, motion, illustration and production design.
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


def route(result: dict, alert: int, ask: int, rules: dict | None = None) -> tuple[str, str]:
    """Map a scored result to a decision: 'alert' | 'ask' | 'dropped', plus a reason."""
    if result.get("german_required") == "fluent":
        return "dropped", "requires German"
    if result.get("remote_eligibility") == "no":
        return "dropped", "not Berlin / not hirable in Germany"
    if rules and "experience_max_gap" in rules and years_gap(result, rules) > int(rules["experience_max_gap"]):
        return "dropped", f"asks for {result.get('years_required')}+ years of experience"
    sc = int(result["score"])
    if sc < ask:
        return "dropped", f"low score ({sc})"
    if sc < alert or result.get("remote_eligibility") == "unclear":
        return "ask", ""  # an unclear location is a question for Liam, never an alert
    return "alert", ""


def age_points(posted_at: str, now_iso: str, table: dict[int, int], after: int) -> int:
    """Points for how recently the job was posted: the first 'up to N days' row it fits,
    `after` if it's older than all of them, 0 if the post date is unknown."""
    posted, now = _to_dt(posted_at), _to_dt(now_iso)
    if not posted or not now:
        return 0
    days = (now - posted).total_seconds() / 86400
    for max_days, points in sorted((int(d), int(p)) for d, p in table.items()):
        if days <= max_days:
            return points
    return int(after)


def years_gap(result: dict, rules: dict) -> int:
    """Years the post asks for beyond Liam's own years in that discipline."""
    have = (rules.get("liam_years") or {}).get(result.get("discipline") or "product", 0)
    return max(0, int(result.get("years_required") or 0) - int(have))


def adjust(result: dict, rules: dict, age: int = 0) -> tuple[int, list[str]]:
    """Claude's fit score plus Liam's bonuses (Berlin, product design, favourite field,
    a fresh post) and minus the penalties (an old post, years beyond his). Bonuses only
    go to jobs that already fit. Returns the 0-100 score and how it was made up."""
    fit = int(result["score"])
    parts = [("fit", fit)]
    if fit >= int(rules.get("bonus_min_fit", 0)):
        if result.get("remote_eligibility") == "berlin":
            parts.append(("Berlin", int(rules.get("berlin_bonus", 0))))
        role = result.get("role_type", "")
        if (result.get("discipline") or "product") == "product":  # a brand job tagged "product design" doesn't count
            parts.append((role, int((rules.get("role_bonus") or {}).get(role, 0))))
        field = result.get("field", "other")
        parts.append((field, int((rules.get("field_bonus") or {}).get(field, 0))))
        if age > 0:
            parts.append(("new post", age))
    if age < 0:
        parts.append(("old post", age))
    gap = years_gap(result, rules)
    # The penalty for the highest gap reached ({2: 10, 3: 20}: 2 years beyond -> 10).
    off = max((int(p) for g, p in (rules.get("experience_penalty") or {}).items() if gap >= int(g)),
              default=0)
    parts.append((f"asks {result.get('years_required')} yrs", -off))
    parts = [(label, pts) for label, pts in parts if pts or label == "fit"]
    total = max(0, min(100, sum(pts for _, pts in parts)))
    return total, [f"fit {fit}"] + [f"{label} {pts:+d}" for label, pts in parts[1:]]


# Locations that can still suit Liam when a job isn't marked remote.
_OK_PLACES = ("berlin", "germany", "deutschland", "remote", "europe", "emea", "eu",
              "worldwide", "anywhere", "global")


def onsite_outside_berlin(location: str, remote: str) -> bool:
    """True for an office/hybrid job in a named place that isn't Berlin (no Claude call needed)."""
    loc = (location or "").lower()
    if not loc.strip() or remote == "yes":
        return False  # unknown or remote: the Matcher decides
    return not any(re.search(rf"\b{p}\b", loc) for p in _OK_PLACES)


_GERMAN = {"und", "der", "die", "das", "mit", "für", "wir", "du", "dich", "dein", "deine",
           "ihr", "bei", "von", "ist", "eine", "einen", "auf", "zu", "uns", "unser", "unsere",
           "werden", "oder", "nicht", "auch", "als", "sowie", "im", "den", "dem", "des", "bist"}
_ENGLISH = {"and", "the", "with", "for", "we", "you", "your", "our", "is", "are", "to", "of",
            "on", "a", "be", "will", "as", "or", "this", "that", "who", "what"}


def written_in_german(text: str) -> bool:
    """True when the post is mostly German. A German post means German is needed."""
    words = re.findall(r"[a-zäöüß]+", (text or "").lower())
    de = sum(w in _GERMAN for w in words)
    en = sum(w in _ENGLISH for w in words)
    return de >= 20 and de > 1.5 * en


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
