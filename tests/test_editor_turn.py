"""The Editor understanding plain requests and carrying them out (no network, no model)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.editor import act, turn as turn_mod
from agents.editor.act import Env, apply_actions
from agents.editor.context import EditorContext
from agents.editor.converse import build_system
from shared.assets import Asset

PAGE = "407be63a-05ad-8160-bb8f-ed832bc3d9c2"
JID = PAGE.replace("-", "")


def _ctx():
    return EditorContext(PAGE, "Designer", "Acme", "Berlin", "product design", "Post", "", "", "", "guide", "cv")


def _asset(kind, state="needed", text="", first=""):
    return Asset(f"row-{kind}", PAGE, kind, state, kind.upper(), "", text, first or text)


class Notion:
    def __init__(self):
        self.updates = []

    def update_page(self, page_id, props):
        self.updates.append((page_id, props))

    def query_database(self, db, filter=None):
        return []

    def create_page(self, db, props):
        return {"id": "new-row"}

    def job_status(self):
        return [p["Status"]["select"]["name"] for i, p in self.updates if "Status" in p]


class Tg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat, text, buttons=None):
        self.sent.append((text, buttons))
        return {"message_id": 1}


@pytest.fixture
def env(monkeypatch):
    delivered = []
    monkeypatch.setattr(act, "deliver", lambda tg, chat, ctx, asset: delivered.append(asset.kind))
    monkeypatch.setattr(act.drafts, "draft", lambda claude, ctx, asset, history: f"drafted {asset.kind}")
    monkeypatch.setattr(act.drafts, "revise", lambda claude, ctx, asset, instr: (f"{asset.text} edited", "Changed it."))
    e = Env(notion=Notion(), tg=Tg(), chat="42", claude=object(), ctx=_ctx(), ids={"Assets": "assets", "Jobs": "jobs"},
            assets=[_asset("cv"), _asset("loom_script")], history=[])
    e.delivered = delivered
    return e


def _act(kind_type, kind="", instruction=""):
    return {"type": kind_type, "kind": kind, "instruction": instruction, "correction_form": "", "old_line": "",
            "new_line": "", "liams_words": "", "never_line": ""}


def test_full_stop_done_style_message_drafts(env):
    done = apply_actions(env, [_act("draft_asset", "cv")], "Done.")
    assert env.delivered == ["cv"] and "CV" in done.lines[0]
    assert next(a for a in env.assets if a.kind == "cv").text == "drafted cv"


def test_draft_of_asset_not_on_the_list_is_added(env):
    apply_actions(env, [_act("draft_asset", "cover_letter")], "write a letter too")
    assert env.delivered == ["cover_letter"] and any(a.kind == "cover_letter" for a in env.assets)


def test_checklist_items_are_not_drafted(env):
    done = apply_actions(env, [_act("draft_asset", "portfolio")], "do my portfolio")
    assert env.delivered == [] and "yours" in done.lines[0]


def test_skip_one_asset_keeps_the_application(env):
    done = apply_actions(env, [_act("skip_asset", "cv")], "skip the cv")
    assert next(a for a in env.assets if a.kind == "cv").state == "skipped"
    assert env.notion.job_status() == [] and not done.dropped


def test_revise_missing_asset_is_reported_plainly(env):
    done = apply_actions(env, [_act("revise_asset", "cover_letter", "shorter")], "shorter")
    assert "isn't drafted yet" in done.lines[0] and env.delivered == []


def test_revise_an_empty_row_is_reported_plainly(env):
    done = apply_actions(env, [_act("revise_asset", "cv", "shorter")], "shorter")
    assert "isn't drafted yet" in done.lines[0]


def test_revise_changes_only_that_asset(env):
    env.assets[0] = _asset("cv", "drafted", "old cv")
    env.assets[1] = _asset("loom_script", "drafted", "old loom")
    done = apply_actions(env, [_act("revise_asset", "cv", "shorter")], "shorter")
    assert env.assets[0].text == "old cv edited" and env.assets[1].text == "old loom"
    assert env.delivered == ["cv"] and "Changed it." in done.lines[0]


def test_revise_without_a_kind_uses_the_only_draft(env):
    env.assets[1] = _asset("loom_script", "drafted", "old loom")
    apply_actions(env, [_act("revise_asset", "", "shorter")], "shorter")
    assert env.assets[1].text == "old loom edited"


def test_unclear_asset_asks_which_one(env):
    env.assets[0] = _asset("cv", "drafted", "a")
    env.assets[1] = _asset("loom_script", "drafted", "b")
    done = apply_actions(env, [_act("revise_asset", "", "shorter")], "shorter")
    assert "Which" in done.lines[0] and env.delivered == []


def test_action_failure_is_reported_not_hidden(env, monkeypatch):
    def boom(*a):
        raise RuntimeError("model down")
    monkeypatch.setattr(act.drafts, "draft", boom)
    done = apply_actions(env, [_act("draft_asset", "cv"), _act("skip_asset", "loom_script")], "go")
    assert "couldn't" in done.lines[0]
    assert next(a for a in env.assets if a.kind == "loom_script").state == "skipped"


def test_needs_input_is_passed_on(env, monkeypatch):
    def need(*a):
        raise act.drafts.NeedsInput("Paste the form's questions here.")
    monkeypatch.setattr(act.drafts, "draft", need)
    assert apply_actions(env, [_act("draft_asset", "form_answers")], "go").lines == ["Paste the form's questions here."]


def test_mixed_message_runs_every_action_in_order(env, monkeypatch):
    order = []
    monkeypatch.setattr(act, "_correct", lambda e, a, m, b: order.append("saved"))
    real = env.notion.update_page
    env.notion.update_page = lambda i, p: (order.append("dropped") if "Status" in p else None, real(i, p))
    done = apply_actions(env, [_act("save_correction"), _act("drop_application")], "Save that. Drop it.")
    assert order == ["saved", "dropped"] and done.dropped


def test_drop_sets_skipped_and_offers_bring_back(env):
    apply_actions(env, [_act("drop_application")], "drop")
    assert env.notion.job_status() == ["Skipped"]
    assert env.tg.sent[0][1] == [[("↩️ Bring it back", f"restore:{JID}")]]


def test_nothing_runs_after_a_drop(env):
    apply_actions(env, [_act("drop_application"), _act("draft_asset", "cv")], "drop")
    assert env.delivered == []


def test_list_jobs_sends_the_real_list(env, monkeypatch):
    called = []
    monkeypatch.setattr(act, "_list_jobs", lambda e: called.append(True))
    apply_actions(env, [_act("list_jobs")], "other jobs?")
    assert called == [True]


def test_mark_final_counts_lines_and_saves_reference_for_cv_and_letter_only(env, monkeypatch):
    saved = []
    monkeypatch.setattr(act.learn, "save_reference", lambda *a: saved.append(a[2]))
    env.assets[0] = _asset("cv", "drafted", "line one\nline two changed", "line one\nline two")
    env.assets[1] = _asset("loom_script", "drafted", "same")
    done = apply_actions(env, [_act("mark_final", "cv"), _act("mark_final", "loom_script")], "both final")
    assert saved == ["CV"]
    assert env.assets[0].state == "final" and env.assets[1].state == "final"
    assert ("row-cv", {"Lines changed": {"number": 1}}) in env.notion.updates
    assert "1 line" in done.lines[0]


def test_mark_final_needs_a_draft(env):
    assert "isn't drafted yet" in apply_actions(env, [_act("mark_final", "cv")], "final").lines[0]


def test_turn_shows_the_model_each_asset_and_returns_actions():
    calls = []

    class Model:
        def json_call(self, system, user, schema, **k):
            calls.append((system, user, schema))
            return {"reply": "On it.", "actions": []}

    assets = [_asset("cv", "drafted", "My CV text"), _asset("loom_script")]
    out = turn_mod.turn(Model(), _ctx(), [{"role": "user", "content": "Make it shorter"}], assets)
    assert out == {"reply": "On it.", "actions": []}
    assert "My CV text" in calls[0][1] and "Make it shorter" in calls[0][1] and "loom_script" in calls[0][1]


def test_schema_covers_every_action():
    types = set(turn_mod.TURN_SCHEMA["properties"]["actions"]["items"]["properties"]["type"]["enum"])
    assert types == {"draft_asset", "revise_asset", "skip_asset", "mark_final", "drop_application",
                     "list_jobs", "save_correction"}


def test_system_prompt_lists_real_abilities_and_old_commands_are_gone():
    system = build_system(_ctx())
    assert "code carries out" in system
    assert 'reply "drop"' not in system and "Want me to add this to mytone" not in system


def test_new_draft_reports_what_the_check_still_found(env, monkeypatch):
    monkeypatch.setattr(act.converse, "voice_issues", lambda ctx, text, kind: ["dash in a sentence"])
    done = apply_actions(env, [_act("draft_asset", "loom_script")], "go")
    assert "Heads up" in done.lines[0] and "dash" in done.lines[0]


def test_revised_loom_script_is_checked_too(env, monkeypatch):
    env.assets[1] = _asset("loom_script", "drafted", "old loom")
    monkeypatch.setattr(act.converse, "voice_issues", lambda ctx, text, kind: ["dash in a sentence"])
    assert "Heads up" in apply_actions(env, [_act("revise_asset", "loom_script", "x")], "x").lines[0]
