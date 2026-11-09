"""Write the Director's brief and work out which assets a job needs.

The brief tells Liam what the company is after, who they want and why he fits. It
isn't a source of facts for anything else. Every "why you" point has to quote his
CV or voice guide, and code removes any point whose quote isn't really there.
"""

from __future__ import annotations

import html
from typing import Optional

from shared.assets import CHECKLIST_KINDS, DRAFTED_KINDS, LABELS, Planned
from shared.quotes import appears_in

_KIND = {"loom_or_video": "loom_script", "form_questions": "form_answers"}
_STATE = {"required": "needed", "optional": "optional"}
_FIELD_LIMITS = (500, 350, 250, 150)  # longest line first, tighter only if the brief won't fit one message
_MESSAGE_LIMIT = 4000

BRIEF_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "after_they_say": {"type": "array", "items": {"type": "string"},
                           "description": "Up to 2 exact quotes from the post showing what the company is after."},
        "after_my_read": {"type": "string", "description": "What you read into it, one or two lines. '' if nothing."},
        "candidate_they_say": {"type": "array", "items": {"type": "string"},
                               "description": "Up to 2 exact quotes from the post describing who they want."},
        "candidate_my_read": {"type": "string", "description": "What you read into it. '' if nothing."},
        "why_you": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "point": {"type": "string", "description": "Why he solves their problem, one line, said to him as 'you'."},
                "project": {"type": "string", "description": "The real project or job it comes from."},
                "source_quote": {"type": "string", "description": "5 to 12 words copied exactly from his CV or voice guide that prove it."},
            },
            "required": ["point", "project", "source_quote"],
        }},
        "weak_spots": {"type": "array", "items": {"type": "string"},
                       "description": "Where the post asks for something his sources don't show. Up to 3."},
    },
    "required": ["after_they_say", "after_my_read", "candidate_they_say", "candidate_my_read", "why_you", "weak_spots"],
}

SYSTEM = """You are Liam Hasson's Director. A job has reached him and he wants to know
what he'd be walking into. You don't write his application. You brief him, in short.

Tell him what the company is after, who they want, and what makes him the answer to
their problem, using only his history, experience and skills.

RULES
- "They say" fields are exact quotes from the job post, copied word for word.
- "My read" fields are your interpretation. Keep them apart from what the post says.
  If the post doesn't support a read, leave it empty instead of guessing.
- Every why_you point names a real project or job and quotes the exact words from his
  CV or voice guide that prove it. No quote, no point. At most 4 points, strongest first.
- Never claim he has used their product, knows their team, or has feelings about
  their brand unless his sources say so.
- weak_spots are for him only. Be straight about what his sources don't show.
- Plain, short lines, said to him as "you". No slogans, no metaphors, no dashes.
"""


def plan_assets(asks: list[dict], form: Optional[list[dict]]) -> list[Planned]:
    """What this job needs, from the post's words and the published form where there is one."""
    states: dict[str, tuple[str, str]] = {}
    refused = set()
    for a in asks or []:
        kind = _KIND.get(a["kind"], a["kind"])
        if a["state"] == "not_wanted":
            refused.add(kind)
        else:
            states[kind] = (_STATE[a["state"]], a.get("quote", ""))

    questions = []
    for q in form or []:
        label, state = q["label"].lower(), "needed" if q["required"] else "optional"
        if "resume" in label or label == "cv":
            states["cv"] = (state, q["label"])
        elif "cover letter" in label:
            states["cover_letter"] = (state, q["label"])
        elif "portfolio" in label:
            states["portfolio"] = (state, q["label"])
        elif "linkedin" in label:
            states["linkedin"] = (state, q["label"])
        else:
            questions.append(q)
    if questions:
        states["form_answers"] = ("needed" if any(q["required"] for q in questions) else "optional",
                                  questions[0]["label"])

    if not states and not refused:  # the post doesn't say, so offer the usual two and let Liam choose
        states = {"cv": ("optional", ""), "cover_letter": ("optional", "")}
    return [Planned(k, states[k][0], LABELS[k], states[k][1])
            for k in DRAFTED_KINDS + CHECKLIST_KINDS if k in states and k not in refused]


def write_brief(claude, *, title: str, company: str, post: str, research: str, cv: str, mytone: str) -> dict:
    user = (f"Role: {title}\nCompany: {company}\n\n=== JOB POST ===\n{post}\n=== END POST ===\n\n"
            f"=== COMPANY RESEARCH ===\n{research or '(none)'}\n=== END RESEARCH ===\n\n"
            f"=== HIS CV ===\n{cv or '(none)'}\n=== END CV ===\n\n"
            f"=== HIS VOICE GUIDE AND STORIES ===\n{mytone}\n=== END GUIDE ===")
    return claude.json_call(SYSTEM, user, BRIEF_SCHEMA, tool_name="submit_brief", max_tokens=1500, temperature=0.2)


def verified_brief(raw: dict, cv: str, mytone: str, post: Optional[str] = None) -> dict:
    """Remove every point and quote whose words aren't really in the source."""
    sources = f"{cv}\n{mytone}"
    brief = {**raw, "why_you": [p for p in raw.get("why_you", []) if appears_in(p.get("source_quote", ""), sources)]}
    if post is not None:
        for field in ("after_they_say", "candidate_they_say"):
            brief[field] = [q for q in raw.get(field, []) if appears_in(q, post)]
    return brief


def _short(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return html.escape(text if len(text) <= limit else text[:limit - 1].rstrip() + "…", quote=False)


def _section(title: str, says: list[str], read: str, limit: int) -> list[str]:
    lines = [f"<b>{title}</b>"]
    if says:
        lines.append("They say: " + " ".join(f"“{_short(q, limit)}”" for q in says[:2]))
    if read:
        lines.append(f"My read: {_short(read, limit)}")
    return lines + [""]


def _compose(brief: dict, planned: list[Planned], form_checked: bool, title: str, company: str, limit: int) -> str:
    lines = [f"🎬 <b>{_short(title, limit)}</b> at <b>{_short(company, limit)}</b>", ""]
    lines += _section("What they're after", brief.get("after_they_say", []), brief.get("after_my_read", ""), limit)
    lines += _section("The candidate they want", brief.get("candidate_they_say", []),
                      brief.get("candidate_my_read", ""), limit)

    if brief.get("why_you"):
        lines.append("<b>Why you</b>")
        lines += [f"• {_short(p['point'], limit)} <i>({_short(p['project'], limit)})</i>" for p in brief["why_you"][:4]]
        lines.append("")
    if brief.get("weak_spots"):
        lines.append("<b>Weak spots</b>")
        lines += [f"• {_short(w, limit)}" for w in brief["weak_spots"][:3]]
        lines.append("")

    lines.append("<b>What to send</b>")
    if not any(p.quote for p in planned):
        lines.append("The post doesn't say what to send.")
    for p in planned:
        note = "" if p.kind in DRAFTED_KINDS else ", yours to handle"
        lines.append(f"• {html.escape(p.label)} ({'required' if p.state == 'needed' else 'optional'}{note})")
    if not form_checked:
        lines.append("I couldn't check the application form. Paste its questions here and I'll answer them.")
    lines += ["", "Where do you want to start? Tap below or just text me."]
    return "\n".join(lines)


def brief_message(brief: dict, planned: list[Planned], form_checked: bool, jid: str,
                  title: str, company: str) -> tuple[str, list]:
    text = ""
    for limit in _FIELD_LIMITS:
        text = _compose(brief, planned, form_checked, title, company, limit)
        if len(text) < _MESSAGE_LIMIT:
            break
    buttons = [[(f"✍️ {p.label}", f"start:{jid}:{p.kind}"), ("⏭ Skip", f"skipasset:{jid}:{p.kind}")]
               for p in planned if p.kind in DRAFTED_KINDS]
    return text, buttons
