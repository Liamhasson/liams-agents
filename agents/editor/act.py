"""Carry out what Liam's message asked for, then report what really happened.

The model only says what should happen. Code does it, and these lines are what
Liam reads afterwards, so he's never told something was done when it wasn't.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from shared.assets import (CHECKLIST_KINDS, DRAFTED_KINDS, LABELS, Asset, Planned, create_assets, find, save_text,
                           set_state)
from .context import EditorContext
from .deliver import deliver
from . import converse, corrections, drafts, learn


@dataclass
class Env:
    notion: object
    tg: object
    chat: object
    claude: object
    ctx: EditorContext
    ids: dict
    assets: list[Asset]
    history: list[dict] = field(default_factory=list)


@dataclass
class Done:
    lines: list[str] = field(default_factory=list)
    dropped: bool = False


def _replace(env: Env, asset: Asset) -> Asset:
    env.assets[:] = [asset if a.kind == asset.kind else a for a in env.assets]
    return asset


def _target(env: Env, kind: str) -> Optional[Asset]:
    """The asset meant: the named one, or the only one with text when he didn't say."""
    if kind:
        return find(env.assets, kind)
    written = [a for a in env.assets if a.text]
    return written[0] if len(written) == 1 else None


def _not_drafted(kind: str) -> str:
    return f"{LABELS.get(kind, 'That')} isn't drafted yet, so there's nothing to change. Tell me to draft it first."


def _draft(env: Env, action: dict) -> str:
    kind = action["kind"]
    if not kind:
        return "Which one should I write?"
    if kind in CHECKLIST_KINDS:
        return f"{LABELS[kind]} is yours to handle, so I won't draft it."
    asset = find(env.assets, kind)
    if asset is None:
        asset = create_assets(env.notion, env.ids["Assets"], env.ctx.job_page_id,
                              [Planned(kind, "needed", LABELS[kind], "")])[0]
        env.assets.append(asset)
    try:
        text = drafts.draft(env.claude, env.ctx, asset, env.history)
    except drafts.NeedsInput as e:
        return str(e)
    asset = _replace(env, save_text(env.notion, asset, text))
    deliver(env.tg, env.chat, env.ctx, asset)
    return f"That's your {asset.label}. Tell me what to change."


def _revise(env: Env, action: dict) -> str:
    kind = action["kind"]
    asset = _target(env, kind)
    if asset is None and not kind:
        return "Which one should I change?"
    if asset is None or not asset.text:
        return _not_drafted(kind or asset.kind)
    text, note = drafts.revise(env.claude, env.ctx, asset, action["instruction"])
    asset = _replace(env, save_text(env.notion, asset, text))
    deliver(env.tg, env.chat, env.ctx, asset)
    if asset.kind in ("cv", "cover_letter"):
        label = "CV" if asset.kind == "cv" else "cover letter"
        issues = converse.voice_issues(env.ctx, text, label)
        if issues:
            note += f" Heads up, the check found: {', '.join(sorted(set(issues)))}"
    return note


def _skip(env: Env, action: dict) -> str:
    asset = _target(env, action["kind"])
    if asset is None:
        return "Which one should I skip?"
    _replace(env, set_state(env.notion, asset, "skipped"))
    return f"Skipped {asset.label}. The rest of the application stays open."


def _finish(env: Env, action: dict) -> str:
    kind = action["kind"]
    asset = _target(env, kind)
    if asset is None and not kind:
        return "Which one is final?"
    if asset is None or not asset.text:
        return _not_drafted(kind or asset.kind)
    doc = "CV" if asset.kind == "cv" else "cover letter"
    changed = len(learn.diff(asset.first_draft, asset.text, doc))
    env.notion.update_page(asset.page_id, {"Lines changed": {"number": changed}})
    if asset.kind in ("cv", "cover_letter"):
        name = "resume" if asset.kind == "cv" else "cover letter"
        learn.save_reference(env.notion, f"{env.ctx.company} {name}", doc, env.ctx.company, env.ctx.title,
                             env.ctx.role_type, asset.text)
    _replace(env, set_state(env.notion, asset, "final"))
    return f"{asset.label} is final. You changed {changed} line{'' if changed == 1 else 's'} from my first draft."


def _drop(env: Env) -> None:
    ctx = env.ctx
    env.notion.update_page(ctx.job_page_id, {"Status": {"select": {"name": "Skipped"}}})
    env.tg.send_message(env.chat, f"Dropped <b>{html.escape(ctx.title, quote=False)}</b> at "
                                  f"{html.escape(ctx.company, quote=False)}.",
                        [[("↩️ Bring it back", f"restore:{ctx.job_page_id.replace('-', '')}")]])


def _list_jobs(env: Env) -> None:
    from agents.messenger.handle import Handler, alert_threshold
    Handler(env.tg, env.notion, env.ids, env.chat)._list_jobs(alert_threshold())


def _correct(env: Env, action: dict, message: str, before: dict[str, str]) -> None:
    """Save it to the voice guide with no message to Liam. The next draft can use it straight away."""
    kind = action["kind"]
    text = before.get(kind, "") if kind else "\n".join(before.values())
    tag = f"{env.ctx.company}, {LABELS.get(kind, 'general')}, {date.today().isoformat()}"
    line = corrections.save(env.notion, action, message, text, tag)
    if line:
        env.ctx.mytone += "\n" + line


_ACTIONS = {"draft_asset": _draft, "revise_asset": _revise, "skip_asset": _skip, "mark_final": _finish}
_FAILED = {"draft_asset": "write that", "revise_asset": "make that change", "skip_asset": "skip that",
           "mark_final": "mark that final", "drop_application": "drop this application", "list_jobs": "list your jobs",
           "save_correction": "save that"}


def apply_actions(env: Env, actions: list[dict], message: str) -> Done:
    """Run each action in order. One failing doesn't stop the rest, and Liam is told about it."""
    done = Done()
    before = {a.kind: a.text for a in env.assets}
    for action in actions:
        kind = action["type"]
        try:
            if kind == "drop_application":
                _drop(env)
                done.dropped = True
                break
            if kind == "list_jobs":
                _list_jobs(env)
            elif kind == "save_correction":
                _correct(env, action, message, before)
            else:
                done.lines.append(_ACTIONS[kind](env, action))
        except Exception as e:
            print(f"  ! {kind} failed: {e}")
            line = f"⚠️ I couldn't {_FAILED[kind]} ({type(e).__name__}). Nothing is lost, so try asking again."
            if line not in done.lines:
                done.lines.append(line)
    return done
