"""One turn of the chat: what the Editor says, and what Liam's message asks to be done."""

from __future__ import annotations

from shared.assets import CHECKLIST_KINDS, DRAFTED_KINDS, Asset
from . import converse
from .context import EditorContext

ACTION_TYPES = ["draft_asset", "revise_asset", "skip_asset", "mark_final", "drop_application",
                "list_jobs", "save_correction"]

TURN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "A short Telegram message to Liam. Never claims an action is done."},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ACTION_TYPES},
                    "kind": {"type": "string", "enum": ["", *DRAFTED_KINDS, *CHECKLIST_KINDS]},
                    "instruction": {"type": "string", "description": "For revise_asset: what to change, in his words."},
                    "correction_form": {"type": "string", "enum": ["", "wording", "instruction", "fact_or_rule"]},
                    "old_line": {"type": "string", "description": "The exact line in the asset being corrected."},
                    "new_line": {"type": "string", "description": "His replacement, copied from his message."},
                    "liams_words": {"type": "string", "description": "His instruction, fact or rule, copied word for word."},
                    "never_line": {"type": "string", "description": "A line he said never to use again, else ''."},
                },
                "required": ["type", "kind", "instruction", "correction_form", "old_line", "new_line",
                             "liams_words", "never_line"],
            },
        },
    },
    "required": ["reply", "actions"],
}

_INSTRUCTIONS = """Liam's last message is at the end of the conversation above. Answer it and list what it asks for.

- reply: talk to him normally, in short Telegram messages. Say what you're about to do, or discuss. Never say something
  is done, because code does it and reports the result right after your reply.
- actions: everything his message asks for, in the order he'd expect. One message can ask for several things. If he
  gives you a fact or a rule, put its save_correction first so the next draft can use it.
- draft_asset writes or rewrites a whole asset. revise_asset changes part of one. Use the kind he means, or '' if you
  can't tell.
- save_correction: use one each time he corrects wording, tells you how something should read, or states a fact or a
  rule about himself. Copy his words exactly and never explain why he changed something.
  wording = he gave the new line (old_line and new_line).
  instruction = he said how to change it (liams_words and old_line).
  fact_or_rule = he stated something true about himself or how he writes (liams_words).
  Choosing what to write about for this one job isn't a correction.
- If he only wants to talk it through, return no actions."""


def _assets_block(assets: list[Asset]) -> str:
    out = []
    for a in assets:
        out.append(f"--- {a.kind} ({a.label}), state: {a.state}, the post's words: {a.quote or 'none'}\n{a.text or '(not drafted)'}")
    return "\n".join(out) or "(none)"


def turn(claude, ctx: EditorContext, history: list[dict], assets: list[Asset]) -> dict:
    convo = "\n".join(f"{'Liam' if m['role'] == 'user' else 'You'}: {m['content']}" for m in history)
    user = f"=== THIS APPLICATION'S ASSETS ===\n{_assets_block(assets)}\n=== END ASSETS ===\n\nCONVERSATION:\n{convo}\n\n{_INSTRUCTIONS}"
    return claude.json_call(converse.build_system(ctx), user, TURN_SCHEMA, tool_name="submit_turn",
                            max_tokens=1500, temperature=converse.WRITER_TEMP)
