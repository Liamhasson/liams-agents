"""Write and change one asset at a time.

A new draft goes through the fact check and voice check. A change Liam asks for
touches only that asset and uses his words exactly, so there's no rewrite loop.
"""

from __future__ import annotations

import json
import re

from shared.assets import Asset
from . import converse
from .context import EditorContext

# Short answers like "Berlin" have nothing for the voice check to work on.
_MIN_WORDS_TO_CHECK = 8
# A change returning under this share of a long asset is a message to Liam, not the asset.
_SHORTEST_SHARE = 0.4
_LONG_ASSET = 400

_TEXT = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

_VOICE_PLAN = {
    "type": "array",
    "description": "Fill this FIRST. One item per paragraph, planned from the voice guide before writing.",
    "items": {
        "type": "object",
        "properties": {
            "purpose": {"type": "string"},
            "modelled_on": {"type": "string", "description": "The exact example line it copies."},
            "facts": {"type": "array", "items": {
                "type": "object",
                "properties": {"claim": {"type": "string"},
                               "source_quote": {"type": "string", "description": "Exact words that prove it."}},
                "required": ["claim", "source_quote"],
            }},
        },
        "required": ["purpose", "modelled_on", "facts"],
    },
}
_LETTER = {"type": "object", "properties": {"voice_plan": _VOICE_PLAN, "text": {"type": "string"}},
           "required": ["voice_plan", "text"]}

_ANSWER_ITEMS = {"type": "array", "items": {
    "type": "object",
    "properties": {"question": {"type": "string"},
                   "answer": {"type": "string", "description": "'' if his sources don't answer it."}},
    "required": ["question", "answer"],
}}
_FORM = {"type": "object", "properties": {"answers": _ANSWER_ITEMS}, "required": ["answers"]}

_REVISED = {"type": "object", "properties": {"text": {"type": "string"}, "note": {"type": "string"}},
            "required": ["text", "note"]}
_REVISED_FORM = {"type": "object", "properties": {"answers": _ANSWER_ITEMS, "note": {"type": "string"}},
                 "required": ["answers", "note"]}

_ASK = {
    "cv": "Write his CV for this job, tailored but true.\n\n" + converse.CV_FORMAT,
    "cover_letter": ("Write his cover letter for this job. First fill voice_plan: for each paragraph pick the "
                     "move, quote the real example line you'll model it on, and quote the source for every "
                     "fact. Only then write the letter from that plan."),
    "loom_script": ("Write the script for the video this post asks for. Cover the sections the post asks for and "
                    "respect any length it gives. Five minutes is about 650 spoken words. Plain text only, "
                    "no markdown, no title and no separators. Put what's on screen in [CAPS] on its own line. Only describe real projects from his sources, and never claim "
                    "something works that his sources don't show working."),
    "form_answers": ("Answer each application form question below in his voice. Free text answers run 80 to 150 "
                     "words. If his sources don't answer a question, leave its answer as ''. Never guess."),
}


class NeedsInput(Exception):
    """The asset can't be drafted until Liam gives something. The message says what."""


def _plain(text: str) -> str:
    """Telegram shows markdown as stray symbols, and a script is read aloud."""
    text = re.sub(r"^\s*(-{3,}|\*{3,})\s*$", "", text.replace("**", ""), flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _history(history: list[dict]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in history) or "(nothing yet)"


def _form_questions(ctx: EditorContext) -> str:
    return "\n".join(f"- {q['label']}{' (required)' if q.get('required') else ''}" for q in ctx.form_questions)


def _draft_form(claude, ctx: EditorContext, history: list[dict]) -> str:
    known = _form_questions(ctx)
    pasted = _history(history)
    user = (f"{_ASK['form_answers']}\n\nQUESTIONS:\n{known or '(use the questions Liam pasted in the conversation)'}"
            f"\n\nCONVERSATION:\n{pasted}")
    res = claude.json_call(converse.build_system(ctx, with_references=True), user, _FORM,
                           tool_name="submit_answers", max_tokens=6000, temperature=converse.WRITER_TEMP)
    answers = res.get("answers") or []
    if not answers:
        raise NeedsInput("Paste the form's questions here and I'll answer them.")
    for item in answers:
        if len(item["answer"].split()) >= _MIN_WORDS_TO_CHECK:
            item["answer"] = converse.enforce_voice(claude, ctx, item["answer"], "form answer")
    return json.dumps(answers, ensure_ascii=False)


def draft(claude, ctx: EditorContext, asset: Asset, history: list[dict]) -> str:
    """A checked first draft of this asset."""
    if asset.kind == "form_answers":
        return _draft_form(claude, ctx, history)
    schema = _LETTER if asset.kind == "cover_letter" else _TEXT
    user = f"{_ASK[asset.kind]}\n\nCONVERSATION:\n{_history(history)}"
    res = claude.json_call(converse.build_system(ctx, with_references=True), user, schema,
                           tool_name="submit_draft", max_tokens=6000, temperature=converse.WRITER_TEMP)
    label = "CV" if asset.kind == "cv" else "cover letter"
    text = _plain(res["text"]) if asset.kind == "loom_script" else res["text"]
    return converse.enforce_voice(claude, ctx, text, label)


def revise(claude, ctx: EditorContext, asset: Asset, instruction: str) -> tuple[str, str]:
    """Apply one change to this asset. Returns (new text, a short note for Liam)."""
    user = (f"Here is his {asset.label}. Liam asked for a change. Make it now. Do not offer options or ask "
            "him to choose, and return the full asset after the change. Apply ONLY what he asked. If he gives "
            "exact words, use them exactly. Keep every other line word for word. If his change needs a fact "
            "that isn't in his sources, keep the old line and say so in the note.\n\n"
            f"=== {asset.label.upper()} ===\n{asset.text}\n=== END ===\n\nLIAM'S CHANGE:\n{instruction}")
    if asset.kind == "form_answers":
        res = claude.json_call(converse.build_system(ctx), user, _REVISED_FORM,
                               tool_name="submit_revision", max_tokens=6000, temperature=0)
        return json.dumps(res["answers"], ensure_ascii=False), res["note"]
    res = claude.json_call(converse.build_system(ctx), user, _REVISED,
                           tool_name="submit_revision", max_tokens=6000, temperature=0)
    if len(asset.text) >= _LONG_ASSET and len(res["text"]) < len(asset.text) * _SHORTEST_SHARE:
        return asset.text, "I didn't apply that, because the result wasn't a full version. Try asking again."
    return res["text"], res["note"]
