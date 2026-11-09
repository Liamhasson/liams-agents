"""Corrections go silently into mytone, in Liam's own words only (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.editor import corrections, mytone
from agents.editor.act import Env, apply_actions
from agents.editor.context import EditorContext
from agents.editor.corrections import entry, save
from shared.assets import Asset

TAG = "Acme, CV, 2026-11-09"


def _a(form="", old="", new="", words="", never=""):
    return {"type": "save_correction", "kind": "cv", "instruction": "", "correction_form": form, "old_line": old,
            "new_line": new, "liams_words": words, "never_line": never}


def test_wording_entry_stores_old_and_his_new_line():
    e = entry(_a("wording", "I invented it.", "I built it."), 'Change it to "I built it."', "I invented it. More.", TAG)
    assert '"I invented it."' in e and '"I built it."' in e and "Acme, CV" in e


def test_instruction_stores_his_exact_words():
    e = entry(_a("instruction", "A long opening line here.", words="make this shorter"),
              "make this shorter please", "A long opening line here. More.", TAG)
    assert '"make this shorter"' in e and "A long opening line here." in e


def test_general_instruction_needs_no_line():
    assert '"keep it plain"' in entry(_a("instruction", words="keep it plain"), "keep it plain", "text", TAG)


def test_fact_or_rule_stores_his_exact_words():
    e = entry(_a("fact_or_rule", words="I'm freelancing on a new project contract"),
              "I'm freelancing on a new project contract.", "", TAG)
    assert "I'm freelancing on a new project contract" in e


def test_model_paraphrase_is_not_saved():
    assert entry(_a("fact_or_rule", words="He prefers short lines"), "keep it short", "", "t") is None


def test_replacement_must_be_his_words():
    assert entry(_a("wording", "I invented it.", "I crafted a bold solution."), "fix it", "I invented it.", TAG) is None


def test_old_line_must_exist_in_the_asset():
    assert entry(_a("wording", "A line that was never there.", "I built it."), 'say "I built it."', "Other text.", TAG) is None


def test_no_form_means_nothing_saved():
    assert entry(_a(), "hello", "", TAG) is None


def test_no_reason_is_ever_written():
    e = entry(_a("wording", "I invented it.", "I built it."), "I built it.", "I invented it.", TAG)
    assert "because" not in e and "reason" not in e.lower()


class Notion:
    def __init__(self, text="1. The short version", fail=False):
        self.text, self.fail, self.appended, self.never = text, fail, [], []

    def load_ids(self):
        return {"mytone": "page", "Never again": "db"}

    def page_text(self, pid):
        return self.text

    def _request(self, method, path, payload=None):
        if self.fail:
            raise RuntimeError("Notion down")
        for child in payload["children"]:
            kind = child["type"]
            line = child[kind]["rich_text"][0]["text"]["content"]
            self.appended.append((kind, line))
            self.text += "\n" + line

    def create_page(self, db, props):
        self.never.append(props)
        return {"id": "n"}


GOOD = _a("wording", "I invented it.", "I built it.")


def test_heading_added_only_once():
    n = Notion()
    save(n, GOOD, "I built it.", "I invented it.", TAG)
    save(n, GOOD, "I built it.", "I invented it.", TAG)
    assert sum(mytone.CORRECTIONS_HEADING in line for _, line in n.appended) == 1
    assert sum(k == "bulleted_list_item" for k, _ in n.appended) == 2


def test_save_returns_the_line_it_wrote():
    assert '"I built it."' in save(Notion(), GOOD, "I built it.", "I invented it.", TAG)


def test_nothing_written_for_a_rejected_entry():
    n = Notion()
    assert save(n, _a("fact_or_rule", words="invented"), "hello", "", TAG) is None and n.appended == []


def test_never_line_goes_to_never_again_only_when_said():
    n = Notion()
    save(n, _a("wording", "I invented it.", "I built it.", never="I invented it."), "never say that. I built it.", "I invented it.", TAG)
    assert len(n.never) == 1 and n.never[0]["Line"]["title"][0]["text"]["content"] == "I invented it."
    n2 = Notion()
    save(n2, GOOD, "I built it.", "I invented it.", TAG)
    assert n2.never == []


class Tg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat, text, buttons=None):
        self.sent.append(text)


def _env(notion):
    ctx = EditorContext("job", "Designer", "Acme", "Berlin", "product design", "", "", "", "", "the guide", "cv")
    return Env(notion=notion, tg=Tg(), chat="42", claude=object(), ctx=ctx, ids={},
               assets=[Asset("r", "job", "cv", "drafted", "CV", "", "I invented it.", "I invented it.")])


ACTION = {**GOOD}


def test_save_sends_no_telegram_message():
    env = _env(Notion())
    done = apply_actions(env, [ACTION], "I built it.")
    assert env.tg.sent == [] and done.lines == []


def test_mytone_reloaded_after_save():
    env = _env(Notion())
    apply_actions(env, [ACTION], "I built it.")
    assert '"I built it."' in env.ctx.mytone


def test_failed_save_is_reported_once():
    env = _env(Notion(fail=True))
    done = apply_actions(env, [ACTION, ACTION], "I built it.")
    assert len(done.lines) == 1 and "couldn't" in done.lines[0]


def test_tag_names_the_company_and_asset():
    n = Notion()
    apply_actions(_env(n), [ACTION], "I built it.")
    assert any("Acme, CV" in line for _, line in n.appended)


def test_correction_uses_the_text_from_before_the_edit(monkeypatch):
    from agents.editor import act
    monkeypatch.setattr(act, "deliver", lambda *a: None)
    monkeypatch.setattr(act.drafts, "revise", lambda c, x, a, i: ("I built it.", "ok"))
    monkeypatch.setattr(act.converse, "voice_issues", lambda *a: [])
    n = Notion()
    env = _env(n)
    revise = {**ACTION, "type": "revise_asset", "instruction": "fix"}
    apply_actions(env, [revise, ACTION], "I built it.")
    assert any('"I invented it."' in line for _, line in n.appended)
