"""The Writer's Sonnet conversation: opening, replies, and final drafts.

Liam's mytone is the voice bible (loaded verbatim). Facts come only from mytone
+ his current CV. Job titles and dates follow the CV; story details follow mytone.

Every final draft goes through three steps (per Liam: correctness over tokens):
1. Plan: each paragraph is mapped to a mytone move, the real example line it's
   modelled on, and the source of every fact, before a word is written.
2. Review: a strict editor re-reads the whole guide and the sources and rewrites
   any sentence that invents something, mentions salary, or reads like a slogan.
3. Lint: deterministic checks (dashes, banned words, commas, salary) as a backstop.
"""

from __future__ import annotations

import re

from shared.claude import Claude
from . import references
from .context import NeverAgain, WriterContext

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

SALARY_WORDS = ["salary", "gross per year", "per annum", "€", "compensation", "k/year"]

# Lines Liam rejected live in the "Never again" database in Notion Private
# (ctx.never_again), not here: the repo is public.

HARD_RULES = """HARD RULES. Obey them in every message and every draft, no exceptions.
Before writing, re-read the whole voice guide below. Before sending, re-check every
sentence against these rules.

TRUTH
- Every claim about Liam must come from his voice guide or his CV below. If you
  can't point to the line it came from, don't write it.
- Never invent, guess or imply anything. That includes saying he has used the
  company's product, knows their team, read something of theirs, or has feelings
  about their brand. The guide's "he's been that user" move only applies where his
  life in sections 8 and 9 shows it (musician, night-train passenger, fitness).
  If there's no real link to the company's users, leave that move out.
- Only say he has used a company's product if his voice guide names that company
  or product. Otherwise he hasn't, so don't say or hint it.
- Job titles and dates follow his CV. Story details and numbers follow the guide.

SALARY
- Never mention salary, pay or a range in a cover letter or CV. Ever.

NO SLOGANS, NO CLEVER LINES
- Never turn the guide's descriptions of Liam into lines about himself, such as
  "That's the part of the work I go looking for" or "I go looking for problems
  nobody pointed at". Show it with a story instead.
- No metaphors or figurative lines. Every sentence says something concrete: a
  fact, a story beat, a specific idea for them, or a plain practical line.
- The closing invitation asks about one specific, real part of their work, like
  the guide's example "I'd love to hear how your team decides what goes into a
  release plan".

VOICE
- Model every paragraph on Liam's real example lines in sections 2, 3 and 7.
  Copy their rhythm and plainness, not the guide's descriptions of him.
- NO dashes of any kind in sentences. No em-dash, no en-dash, no " - ". Use a full
  stop or a connector (because, so, which, and, but).
- At most TWO commas per sentence. If more, split it with a connector.
- No parentheses in letters. Every sentence is a full sentence.
- Never use: actually, exactly, matters, honestly, to be honest, passionate,
  thrilled, excited to apply, delighted, leverage, seamless, robust, AI-native,
  AI-powered, dynamic, results-driven, "I am writing to apply", "I would be a
  great fit", "thank you for your consideration", "I look forward to hearing from
  you". Full list in section 6.
- If it reads like a generic cover letter, it is wrong.
"""

CV_FORMAT = """CV FORMAT. Use exactly this markdown structure. It renders into Liam's own
resume layout, so keep the header, section order and entry style of his CURRENT CV.

# Liam Hasson
<title line from his CV, adjusted to the role only if it stays true>
<contact line from his CV, items separated by " · ">

## Summary
<one paragraph, at most 4 lines>

## Experience
### <Role>, <Company> | <Mon YYYY> - <Mon YYYY or Present>
- <bullet>

## Projects
### <Project>, <Context> | <dates>
_<one italic line describing it>_
- <bullet>

## Skills
**<Group>:** item · item · item

## Education
### <Degree>, <School> | <dates>

## Additional Information
**Certifications:** ...
**Languages:** ...

It must fit one A4 page: at most 4 bullets per role, one line per bullet where
possible. Tailor which bullets and stories lead to this job, but only use facts
from the sources.
"""


def _rejected_block(entries: list[NeverAgain], kind: str | None = None) -> str:
    lines = [f'- "{e.line}" ({e.reason})' for e in entries if e.applies(kind)]
    return "\n".join(lines) or "(none yet)"


REFERENCE_RULES = """APPROVED REFERENCES. These are letters and a CV Liam approved. They are his
real writing and outrank the guide's example lines.
- Openings and closings are never reused. Write them fresh for this company.
- If you tell the same story as a story paragraph below, and every sentence in it is
  still true and fits this job, copy that paragraph word for word.
- Never reuse a paragraph that is about the other company: its name, product, team,
  values or job post.
- If a fact in a reference disagrees with his current CV or voice guide, the CV and
  guide win. Change only that fact and keep the rest word for word.
- In the CV, reuse approved bullet wording where the role and facts are the same."""


def _references_section(ctx: WriterContext, kind: str | None = None) -> str:
    text = references.block(references.pick(ctx), kind)
    return f"\n{REFERENCE_RULES}\n\n=== APPROVED REFERENCES ===\n{text}\n=== END REFERENCES ===\n" if text else ""


def build_system(ctx: WriterContext, with_references: bool = False) -> str:
    refs = _references_section(ctx) if with_references else ""
    return f"""You are Liam Hasson's Writer. You co-write his job application WITH
him over a Telegram chat, then produce his CV and (if he wants one) cover letter.

{HARD_RULES}

LINES LIAM HAS REJECTED. Never write these or anything shaped like them:
{_rejected_block(ctx.never_again)}

Never claim HTML/CSS.

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
{refs}
=== LIAM'S CURRENT CV ===
{ctx.base_cv or '(none found)'}
=== END CV ===

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


def _strip_cv_dates(text: str) -> str:
    """Drop the '| dates' part of CV entry lines so date ranges don't trip the dash check."""
    return "\n".join(l.rsplit(" | ", 1)[0] if l.lstrip().startswith("###") else l
                     for l in text.split("\n"))


def _strip_bullets(text: str) -> str:
    return "\n".join(re.sub(r"^\s*[-*•]\s+", "", l) for l in text.split("\n"))


def _norm(text: str) -> str:
    """Lowercase, straight quotes, single spaces, no closing punctuation: for exact-line matching."""
    text = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().rstrip(".!?").strip()


def lint(text: str, kind: str = "cover letter",
         never_again: list[NeverAgain] | None = None) -> list[str]:
    """Deterministic voice violations that must never ship. `kind` is "cover letter" or "CV"."""
    issues: list[str] = []
    prose = _strip_bullets(_strip_cv_dates(text) if kind == "CV" else text)
    flat = _norm(prose)
    for e in never_again or []:
        if e.applies(kind) and _norm(e.line) and _norm(e.line) in flat:
            issues.append(f"rejected line: {e.line}")
    if "—" in prose or "–" in prose or re.search(r"[ \t]-[ \t]", prose):
        issues.append("dash in a sentence")
    low = prose.lower()
    for w in BANNED:
        if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low):
            issues.append(f"banned word: {w}")
    for w in SALARY_WORDS:
        if w in low:
            issues.append(f"salary mention: {w.strip()}")
            break
    # CV: check each line on its own, skipping headings ("Role, Company" isn't a sentence).
    chunks = ([l for l in prose.split("\n") if not l.lstrip().startswith("#")]
              if kind == "CV" else [prose])
    sentences = [s for c in chunks for s in re.split(r"(?<=[.!?])\s+", c)]
    for sent in sentences:
        if re.sub(r"(?<=\d),(?=\d)", "", sent).count(",") > 2:  # 3,172 isn't a comma
            issues.append("3+ commas in a sentence")
            break
    if kind != "CV" and re.search(r"\(.+?\)", prose):
        issues.append("parentheses in a letter")
    return issues


def voice_issues(ctx: WriterContext, text: str, kind: str) -> list[str]:
    """The lint for a real draft: rejected lines everywhere, style rules except on approved sentences."""
    style = lint(references.without_approved(text, references.pick(ctx), kind), kind)
    rejected = [i for i in lint(text, kind, ctx.never_again) if i.startswith("rejected line")]
    return sorted(set(style + rejected))


_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "problems": {
            "type": "array",
            "description": "Every sentence that breaks a rule. Empty if the draft is clean.",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "kind": {"type": "string", "enum": [
                        "invented_or_unsupported_fact", "salary", "slogan_or_vague",
                        "generic_cover_letter", "voice_rule_break"]},
                    "why": {"type": "string"},
                },
                "required": ["sentence", "kind", "why"],
            },
        },
        "corrected": {"type": "string",
                      "description": "The full corrected text ONLY. No commentary, no preamble."},
    },
    "required": ["problems", "corrected"],
}


def review(claude: Claude, ctx: WriterContext, draft: str, label: str,
           lint_issues: list[str]) -> dict:
    """One strict pass: check every sentence against the whole guide and the sources."""
    kind = "CV" if label == "CV" else "cover letter"
    system = (
        f"You are a strict editor for Liam Hasson's {label}. Go through it sentence "
        "by sentence and check each one against his whole voice guide, his CV and "
        "the rules below. For each sentence ask: can I point to the exact source line "
        "for every fact in it? Is it concrete, or is it a slogan or a clever line? "
        "Does it sound like his example lines in sections 2, 3 and 7? Does it break a "
        "voice rule? List every problem, then return the corrected text. Remove "
        "unsupported claims entirely rather than softening them. Rewrite slogans and "
        "vague lines into something concrete from his stories, or cut them. When you "
        "cut a line, make sure the sentences around it still connect. Keep every true "
        "fact, name and number. Keep the CV markdown structure as it is. Sentences "
        "copied word for word from his approved references below are his own words: "
        "keep them as they are unless a fact in them is out of date.\n\n"
        + HARD_RULES
        + "\nLINES LIAM HAS REJECTED:\n" + _rejected_block(ctx.never_again, kind)
        + _references_section(ctx, kind)
        + "\n\n=== VOICE GUIDE ===\n" + ctx.mytone
        + "\n=== END GUIDE ===\n\n=== CURRENT CV ===\n" + (ctx.base_cv or "(none)")
        + "\n=== END CV ===\n\n=== JOB POST AND RESEARCH ===\n"
        + f"{ctx.title} at {ctx.company}\n{ctx.description[:3000]}\n\n{ctx.research or ''}"
        + "\n=== END JOB ==="
    )
    hint =f"The automatic check already found: {', '.join(lint_issues)}\n\n" if lint_issues else ""
    user = f"{hint}{label} to review (return corrected text only):\n\n{draft}"
    return claude.json_call(system, user, _REVIEW_SCHEMA, tool_name="submit_review",
                            max_tokens=4000, temperature=WRITER_TEMP)


_FACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "description": "Every factual claim about Liam or his work in the text.",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "source_quote": {"type": "string",
                                     "description": "Exact words from the guide or CV, or '' if none."},
                    "verdict": {"type": "string", "enum": ["faithful", "distorted", "unsupported"]},
                },
                "required": ["claim", "source_quote", "verdict"],
            },
        },
        "corrected": {"type": "string",
                      "description": "The full text with distorted claims fixed to match the source "
                                     "and unsupported ones removed. Text ONLY, no commentary."},
    },
    "required": ["claims", "corrected"],
}


def fact_check(claude: Claude, ctx: WriterContext, draft: str, label: str) -> dict:
    """Compare every claim against the sources, word for word. Nothing else."""
    system = (
        f"You fact-check a draft of Liam Hasson's {label}. There are three sources "
        "below: SOURCE 1 his current CV, SOURCE 2 his voice guide, and SOURCE 3 the "
        "job post with research notes. Claims about Liam must come from source 1 or "
        "2. Claims about the company must come from source 3.\n"
        "List every factual claim: what he did, made, used, caught, measured, knows or "
        "has experienced, every number, title, date, tool and skill, and what the "
        "company says it wants. For each one, search ALL the sources and quote the "
        "exact words that prove it. Anything stated in his CV, even reworded, is "
        "'faithful'. Mark it 'distorted' only if it merges separate facts, adds a "
        "cause or result no source gives, or stretches what happened. Mark it "
        "'unsupported' only if no source says it, such as a skill nowhere in the "
        "sources or a claim that he has used the company's product.\n"
        "Then return the text with distorted claims rewritten to match the source and "
        "unsupported claims removed. Change nothing else, keep the voice and the CV "
        "markdown structure, and keep the sentences around a cut connected.\n\n"
        "=== SOURCE 1: CURRENT CV ===\n" + (ctx.base_cv or "(none)")
        + "\n=== END SOURCE 1 ===\n\n=== SOURCE 2: VOICE GUIDE (sections 9 to 12 hold his facts) ===\n"
        + ctx.mytone + "\n=== END SOURCE 2 ===\n\n=== SOURCE 3: JOB POST AND RESEARCH ===\n"
        + f"{ctx.title} at {ctx.company}\n{ctx.description[:3000]}\n\n{ctx.research or ''}"
        + "\n=== END SOURCE 3 ==="
    )
    return claude.json_call(system, f"{label} to fact-check:\n\n{draft}", _FACT_SCHEMA,
                            tool_name="submit_fact_check", max_tokens=5000, temperature=0)


def enforce_voice(claude: Claude, ctx: WriterContext, draft: str, label: str,
                  log: list[str] | None = None) -> str:
    """Fact-check and review against the whole guide until both pass, plus the lint.

    Per Liam: always pass a CV/cover letter through the full guide before sending,
    even if it costs more tokens. Correctness over prompting time.
    """
    if not draft.strip():
        return draft
    kind = "CV" if label == "CV" else "cover letter"
    log = log if log is not None else []

    def check_facts(text: str) -> str:
        res = fact_check(claude, ctx, text, label)
        log.extend(f"{label}: [{c['verdict']}] {c['claim']}"
                   for c in res["claims"] if c["verdict"] != "faithful")
        return res["corrected"]

    def check_lint(text: str) -> list[str]:
        return voice_issues(ctx, text, kind)

    def review_voice(text: str) -> tuple[str, bool]:
        res = review(claude, ctx, text, label, check_lint(text))
        log.extend(f"{label}: [{p['kind']}] {p['sentence']}" for p in res["problems"])
        return res["corrected"], not res["problems"]

    # Facts first, then voice, then facts again in case the voice edit stretched one.
    draft = check_facts(draft)
    for _ in range(2):
        draft, clean = review_voice(draft)
        if clean and not check_lint(draft):
            break
    draft = check_facts(draft)
    if check_lint(draft):
        draft, _ = review_voice(draft)
    return draft


FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "voice_plan": {
            "type": "array",
            "description": ("Fill this FIRST. One item per cover letter paragraph, planned "
                            "from the voice guide before writing."),
            "items": {
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "description": "What this paragraph does (section 4)."},
                    "move": {"type": "string", "description": "The section 3 move it uses, if any."},
                    "modelled_on": {"type": "string",
                                    "description": ("The exact example line from sections 2, 3 or 7, or the approved "
                                                   "reference paragraph, it copies.")},
                    "facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "claim": {"type": "string"},
                                "source_quote": {"type": "string",
                                                 "description": "Exact words from the guide or CV that prove it."},
                            },
                            "required": ["claim", "source_quote"],
                        },
                    },
                },
                "required": ["purpose", "modelled_on", "facts"],
            },
        },
        "cv_markdown": {"type": "string",
                        "description": "Final one-page CV in the CV FORMAT markdown."},
        "cover_letter_markdown": {"type": "string",
                                  "description": "Final cover letter, or '' if Liam chose none."},
        "summary": {"type": "string", "description": "One line on what you produced."},
    },
    "required": ["voice_plan", "cv_markdown", "cover_letter_markdown", "summary"],
}


_REVISE_SCHEMA = {
    "type": "object",
    "properties": {
        "cv_markdown": {"type": "string", "description": "The full CV after the change."},
        "cover_letter_markdown": {"type": "string",
                                  "description": "The full cover letter after the change, or '' if none."},
        "note": {"type": "string", "description": "One short line to Liam on what you changed."},
    },
    "required": ["cv_markdown", "cover_letter_markdown", "note"],
}


def revise(claude: Claude, ctx: WriterContext, drafts: dict, request: str) -> dict:
    """Apply Liam's change to the finished pack. Everything he didn't ask about stays word for word.

    No review loop here: if Liam writes a line himself, his words win. The session
    shows him the lint result instead of silently rewriting him.
    """
    user = ("Here is the finished pack. Liam asked for a change. Apply ONLY what he asked. "
            "If he gives exact words, use them exactly. Keep every other line word for word. "
            "If his change needs a fact that isn't in his sources, keep the old line and say "
            "so in the note.\n\n"
            f"=== CV ===\n{drafts['cv_markdown']}\n=== END CV ===\n\n"
            f"=== COVER LETTER ===\n{drafts['cover_letter_markdown'] or '(none)'}\n"
            f"=== END COVER LETTER ===\n\nLIAM'S CHANGE:\n{request}")
    res = claude.json_call(build_system(ctx), user, _REVISE_SCHEMA,
                           tool_name="submit_revision", max_tokens=6000, temperature=0)
    if res["cover_letter_markdown"].strip() == "(none)":
        res["cover_letter_markdown"] = ""
    return res


def finalize(claude: Claude, ctx: WriterContext, history: list[dict]) -> dict:
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    user = ("Produce the FINAL documents now, based on our conversation below.\n"
            "First read the whole voice guide again. Then fill voice_plan: for each "
            "cover letter paragraph pick the move, quote the real example line you'll "
            "model it on, and quote the source for every fact. Only then write the "
            "letter from that plan, and the CV. Use the approved references as the "
            "rules for them say.\n"
            "If Liam chose no cover letter, return '' for cover_letter_markdown and an "
            "empty voice_plan.\n\n" + CV_FORMAT + "\n\nCONVERSATION:\n" + convo)
    drafts = claude.json_call(build_system(ctx, with_references=True), user, FINAL_SCHEMA,
                              tool_name="submit_drafts", max_tokens=6000, temperature=WRITER_TEMP)
    # Mandatory review against the whole guide before anything ships.
    log: list[str] = []
    drafts["cv_markdown"] = enforce_voice(claude, ctx, drafts["cv_markdown"], "CV", log)
    drafts["cover_letter_markdown"] = enforce_voice(
        claude, ctx, drafts["cover_letter_markdown"], "cover letter", log)
    drafts["review_log"] = log
    picked = references.pick(ctx)
    drafts["reused"] = {**references.reused(drafts["cv_markdown"], picked, "CV"),
                        **references.reused(drafts["cover_letter_markdown"], picked, "cover letter")}
    return drafts
