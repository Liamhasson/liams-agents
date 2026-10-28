"""The Writer's Sonnet conversation: opening, replies, and final drafts.

Liam's mytone is the voice bible (loaded verbatim). Facts come only from mytone
+ the base CV; where they conflict, mytone wins (it's the current source of
truth — e.g. Eventread, the Danger Score bands).
"""

from __future__ import annotations

import re

from shared.claude import Claude
from .context import WriterContext

WRITER_TEMP = 0.2  # low: hug Liam's examples, resist generic drift

# Banned words/phrases from mytone §6 (used for a deterministic lint backstop).
BANNED = [
    "actually", "exactly", "it matters", "what matters", "honestly",
    "to be honest", "i'll be honest", "i'll be straight", "let me be upfront",
    "passionate", "thrilled", "excited to apply", "delighted",
    "i am writing to apply", "i would be a great fit", "leverage", "synergy",
    "cutting-edge", "cutting edge", "seamless", "robust", "ai-adjacent",
    "ai-native", "ai-powered", "built for", "dynamic", "results-driven",
    "hit the ground running", "i believe i can add value",
    "thank you for your consideration", "i look forward to hearing from you",
]

HARD_RULES = """HARD VOICE RULES — obey these in every message and every draft,
no exceptions. Re-read the full voice guide below before writing, and re-scan
each line against these before you send it:
- NO em-dashes (—). Use a full stop or a connector (because, so, which, and, but).
- At most TWO commas per sentence. If more, split into sentences joined by a connector.
- Every sentence is a full sentence. Never stack one or two word fragments for effect.
- NEVER use these words: actually, exactly, matters, honestly, to be honest,
  passionate, thrilled, excited to apply, delighted, leverage, seamless, robust,
  AI-native, AI-powered, dynamic, results-driven, "I am writing to apply",
  "I would be a great fit", "thank you for your consideration",
  "I look forward to hearing from you". (Full list in section 6 below.)
- Write like the "Does" column in section 7 and the quoted example lines. Plain,
  direct, first-person, built from a real moment. If it reads like a generic
  cover letter, it is wrong.
"""


def build_system(ctx: WriterContext) -> str:
    return f"""You are Liam Hasson's Writer. You co-write his job application WITH
him over a Telegram chat, then produce his CV and (if he wants one) cover letter.

{HARD_RULES}

Follow his voice exactly. His voice guide is below — treat every rule as binding.
Facts come ONLY from this voice guide and his base CV. Never invent experience,
numbers, tools or people. Where the voice guide and the CV disagree on a fact,
the voice guide wins (it is the current source of truth). Never claim HTML/CSS.

HOW TO TALK TO LIAM (this overrides any generic chat style):
- Short Telegram messages, like a sharp friend helping him prep.
- Lead with the hook idea and the ONE story you'd open with, then ask what he thinks.
- Offer 2 options when there's a real choice, never 5.
- When proposing a change, quote the exact line you'd change, then the new version.
- When he edits something, ask: "Want me to add this to mytone.md?" If he agrees,
  tell him to reply with:  mytone: <the rule>   (that saves it to his voice guide).
- Early on, ask whether he wants a cover letter for this role or just the CV.

=== LIAM'S VOICE GUIDE (mytone.md) ===
{ctx.mytone}
=== END VOICE GUIDE ===

=== LIAM'S BASE CV ===
{ctx.base_cv or '(none found)'}
=== END BASE CV ===

=== THIS JOB ===
Role: {ctx.title}
Company: {ctx.company}
Location: {ctx.location}
Known gaps flagged by the Matcher: {ctx.gaps or 'none'}

Job description:
{ctx.description[:3000]}

Company research notes:
{ctx.research or '(none)'}
=== END JOB ===
"""


def opening(claude: Claude, ctx: WriterContext) -> str:
    kickoff = ("Begin the session for this role. In one short message: ask whether I "
               "want a cover letter or just the CV, then give your hook idea and the one "
               "story you'd lead with, and ask what I think.")
    return claude.chat(build_system(ctx), [{"role": "user", "content": kickoff}], temperature=WRITER_TEMP)


def reply(claude: Claude, ctx: WriterContext, history: list[dict]) -> str:
    return claude.chat(build_system(ctx), history, temperature=WRITER_TEMP)


def lint(text: str) -> list[str]:
    """Deterministic voice violations that must never ship."""
    issues: list[str] = []
    if "—" in text or " – " in text:
        issues.append("em-dash")
    low = text.lower()
    for w in BANNED:
        if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low):
            issues.append(f"banned word: {w}")
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if sent.count(",") > 2:
            issues.append("3+ commas in a sentence")
            break
    return issues


_CORRECT_SCHEMA = {
    "type": "object",
    "properties": {"corrected": {"type": "string",
                                 "description": "The corrected text ONLY — no commentary, no preamble."}},
    "required": ["corrected"],
}


def enforce_voice(claude: Claude, ctx: WriterContext, draft: str, label: str) -> str:
    """Re-read the whole mytone guide and rewrite the draft until it complies.

    Per Liam: always pass a CV/cover letter through the full guide before sending,
    even if it costs more tokens — correctness over prompting time. Uses structured
    output so the editor returns ONLY the corrected text (never its own commentary).
    """
    if not draft.strip():
        return draft
    system = (
        "You are a strict line editor enforcing Liam's voice guide. Rewrite the "
        f"{label} so it obeys EVERY rule in the guide. Do NOT change any facts, "
        "names, numbers or structure. Remove em-dashes (use a full stop or a "
        "connector), remove every banned word from section 6, keep at most two "
        "commas per sentence, make every sentence a full sentence, and match the "
        "'Does' column in section 7. Return via the submit tool, corrected text only.\n\n"
        "=== VOICE GUIDE ===\n" + ctx.mytone + "\n=== END GUIDE ==="
    )
    for _ in range(3):
        issues = lint(draft)
        if not issues:
            break
        user = (f"Fix these violations: {', '.join(issues)}\n\n"
                f"{label} to correct (return corrected text only):\n{draft}")
        res = claude.json_call(system, user, _CORRECT_SCHEMA,
                               tool_name="submit_corrected", max_tokens=3000, temperature=WRITER_TEMP)
        draft = res["corrected"]
    # Last-ditch deterministic cleanup for any em-dash that survived.
    return draft.replace(" — ", ". ").replace("—", ". ").replace(" – ", ". ")


FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "cv_markdown": {"type": "string",
                        "description": "Final one-page CV in markdown, in Liam's voice."},
        "cover_letter_markdown": {"type": "string",
                                  "description": "Final cover letter, or '' if Liam chose none."},
        "summary": {"type": "string", "description": "One line on what you produced."},
    },
    "required": ["cv_markdown", "cover_letter_markdown", "summary"],
}


def finalize(claude: Claude, ctx: WriterContext, history: list[dict]) -> dict:
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    user = ("Based on our conversation below, produce the FINAL documents now, "
            "strictly in Liam's voice and facts. CV must fit one page. If Liam chose "
            "no cover letter, return '' for cover_letter_markdown.\n\n" + convo)
    drafts = claude.json_call(build_system(ctx), user, FINAL_SCHEMA,
                              tool_name="submit_drafts", max_tokens=3000, temperature=WRITER_TEMP)
    # Mandatory voice-enforcement pass over the whole guide before anything ships.
    drafts["cv_markdown"] = enforce_voice(claude, ctx, drafts["cv_markdown"], "CV")
    drafts["cover_letter_markdown"] = enforce_voice(claude, ctx, drafts["cover_letter_markdown"], "cover letter")
    return drafts
