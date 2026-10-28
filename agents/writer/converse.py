"""The Writer's Sonnet conversation: opening, replies, and final drafts.

Liam's mytone is the voice bible (loaded verbatim). Facts come only from mytone
+ the base CV; where they conflict, mytone wins (it's the current source of
truth — e.g. Eventread, the Danger Score bands).
"""

from __future__ import annotations

from shared.claude import Claude
from .context import WriterContext


def build_system(ctx: WriterContext) -> str:
    return f"""You are Liam Hasson's Writer. You co-write his job application WITH
him over a Telegram chat, then produce his CV and (if he wants one) cover letter.

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
    return claude.chat(build_system(ctx), [{"role": "user", "content": kickoff}])


def reply(claude: Claude, ctx: WriterContext, history: list[dict]) -> str:
    return claude.chat(build_system(ctx), history)


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
    return claude.json_call(build_system(ctx), user, FINAL_SCHEMA,
                            tool_name="submit_drafts", max_tokens=3000)
