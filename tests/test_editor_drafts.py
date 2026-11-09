"""Drafting, revising and delivering one asset at a time (no network, no model)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.editor import deliver as delivery, drafts
from agents.editor.context import EditorContext
from agents.editor.deliver import deliver, split_message
from shared.assets import Asset


def _ctx(form=()):
    return EditorContext("job1", "Designer", "Acme", "Berlin", "product design", "Record a Loom of your work.",
                         "They make rockets.", "", "https://acme.com/1", "voice guide", "# Sam\nDesigner\nx\n## Summary\nS",
                         brief="They want a builder.", form_questions=list(form))


def _asset(kind, text="", label="Thing"):
    return Asset("p1", "job1", kind, "needed", label, "", text, text)


class Model:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def json_call(self, system, user, schema, **kw):
        self.calls.append((system, user, schema, kw))
        return self.answer


@pytest.fixture
def voice(monkeypatch):
    seen = []

    def fake(claude, ctx, draft, label, log=None):
        seen.append((label, draft))
        return draft + " [checked]"
    monkeypatch.setattr(drafts.converse, "enforce_voice", fake)
    monkeypatch.setattr(drafts.converse, "fact_check", lambda claude, ctx, draft, label: {"claims": [], "corrected": draft})
    return seen


@pytest.mark.parametrize("kind,label", [("cv", "CV"), ("cover_letter", "cover letter"), ("loom_script", "cover letter")])
def test_each_kind_goes_through_voice_check(voice, kind, label):
    text = drafts.draft(Model({"text": "draft", "voice_plan": []}), _ctx(), _asset(kind), [])
    assert text == "draft [checked]" and voice[0][0] == label


def test_form_answers_go_through_voice_check_when_they_are_real_text(voice):
    long = "I built a tool for bookers because nobody had one to check dates with before."
    out = drafts.draft(Model({"answers": [{"question": "Why us?", "answer": long}]}),
                       _ctx([{"label": "Why us?", "required": True, "type": "textarea"}]), _asset("form_answers"), [])
    assert json.loads(out)[0]["answer"].endswith("[checked]")


def test_short_form_answers_skip_the_voice_check(voice):
    out = drafts.draft(Model({"answers": [{"question": "City?", "answer": "Berlin"}]}),
                       _ctx([{"label": "City?", "required": True, "type": "text"}]), _asset("form_answers"), [])
    assert json.loads(out)[0]["answer"] == "Berlin" and voice == []


def test_form_answers_without_questions_ask_liam_to_paste_them(voice):
    with pytest.raises(drafts.NeedsInput):
        drafts.draft(Model({"answers": []}), _ctx(), _asset("form_answers"), [])


def test_draft_uses_the_conversation(voice):
    model = Model({"text": "draft"})
    drafts.draft(model, _ctx(), _asset("loom_script"), [{"role": "user", "content": "Use the agents project"}])
    assert "Use the agents project" in model.calls[0][1]


def test_loom_prompt_only_allows_real_projects(voice):
    model = Model({"text": "draft"})
    drafts.draft(model, _ctx(), _asset("loom_script"), [])
    assert "real projects" in model.calls[0][1]


def test_revise_touches_only_that_asset():
    model = Model({"text": "new letter", "note": "Done"})
    ctx = _ctx()
    text, note = drafts.revise(model, ctx, _asset("cover_letter", "old letter"), "shorter")
    assert text == "new letter" and note == "Done"
    assert "old letter" in model.calls[0][1] and "=== CV ===" not in model.calls[0][1]


def test_revise_keeps_liams_exact_words(voice):
    model = Model({"text": "new", "note": "Done"})
    drafts.revise(model, _ctx(), _asset("cv", "old"), 'say "I built it"')
    assert "use them exactly" in model.calls[0][1] and voice == []


def test_revise_form_answers_returns_the_same_shape():
    model = Model({"answers": [{"question": "Why?", "answer": "new"}], "note": "ok"})
    text, _ = drafts.revise(model, _ctx(), _asset("form_answers", '[{"question":"Why?","answer":"old"}]'), "x")
    assert json.loads(text) == [{"question": "Why?", "answer": "new"}]


class Tg:
    def __init__(self):
        self.messages, self.docs = [], []

    def send_message(self, chat, text, buttons=None):
        self.messages.append(text)
        return {"message_id": 1}

    def send_document(self, chat, path, caption=""):
        self.docs.append((path, caption))


def test_form_answers_are_one_message_each():
    tg = Tg()
    answers = [{"question": f"Q{i}", "answer": f"A{i}"} for i in range(3)]
    deliver(tg, "42", _ctx(), _asset("form_answers", json.dumps(answers)))
    assert len(tg.messages) == 3 and "<code>A1</code>" in tg.messages[1] and "Q1" in tg.messages[1]


def test_unanswerable_form_question_is_flagged():
    tg = Tg()
    deliver(tg, "42", _ctx(), _asset("form_answers", json.dumps([{"question": "Work permit?", "answer": ""}])))
    assert "Only you can answer" in tg.messages[0] and "Work permit?" in tg.messages[0]


def test_form_text_is_escaped():
    tg = Tg()
    deliver(tg, "42", _ctx(), _asset("form_answers", json.dumps([{"question": "a<b", "answer": "c&d"}])))
    assert "a&lt;b" in tg.messages[0] and "c&amp;d" in tg.messages[0]


def test_cv_and_letter_arrive_as_pdf(monkeypatch):
    monkeypatch.setattr(delivery, "generate_cv_pdf", lambda md, path: path)
    monkeypatch.setattr(delivery, "generate_cover_letter_pdf", lambda text, path, cv_markdown=None: path)
    tg = Tg()
    deliver(tg, "42", _ctx(), _asset("cv", "# Sam", "CV"))
    deliver(tg, "42", _ctx(), _asset("cover_letter", "Hi", "Cover letter"))
    assert len(tg.docs) == 2 and "Acme" in tg.docs[0][1] and tg.messages == []


def test_loom_script_arrives_as_text():
    tg = Tg()
    deliver(tg, "42", _ctx(), _asset("loom_script", "[SHOW SITE]\n\nHi team"))
    assert "Hi team" in tg.messages[0] and tg.docs == []


def test_long_text_splits_on_paragraphs_and_loses_nothing():
    text = "\n\n".join("x" * 1500 for _ in range(6))
    parts = split_message(text)
    assert len(parts) > 1 and all(len(p) <= 4000 for p in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")


def test_one_huge_paragraph_is_still_split():
    parts = split_message("y" * 9000)
    assert all(len(p) <= 4000 for p in parts) and "".join(parts) == "y" * 9000


def test_empty_text_sends_nothing():
    assert split_message("") == []


def test_revise_tells_the_model_to_make_the_change_now():
    model = Model({"text": "new", "note": "Done"})
    drafts.revise(model, _ctx(), _asset("cv", "old"), "x")
    assert "Do not offer options" in model.calls[0][1] and "the full" in model.calls[0][1]


def test_revise_refuses_a_placeholder_instead_of_the_asset():
    long = "A real paragraph of the script. " * 40
    model = Model({"text": "Waiting for Liam's choice.", "note": "Presented two options."})
    text, note = drafts.revise(model, _ctx(), _asset("loom_script", long), "shorten the first sentence")
    assert text == long and "didn't apply" in note


def test_a_short_asset_can_still_shrink():
    text, _ = drafts.revise(Model({"text": "Short.", "note": "ok"}), _ctx(), _asset("cover_letter", "A little longer."), "cut")
    assert text == "Short."


def test_loom_markdown_is_removed(voice):
    raw = "**THE PROBLEM**\n\n---\n\n[SHOW SITE]\n\nHi **team**"
    text = drafts.draft(Model({"text": raw}), _ctx(), _asset("loom_script"), [])
    assert text == "THE PROBLEM\n\n[SHOW SITE]\n\nHi team [checked]"


def test_loom_prompt_asks_for_plain_text(voice):
    model = Model({"text": "x"})
    drafts.draft(model, _ctx(), _asset("loom_script"), [])
    assert "no markdown" in model.calls[0][1]


def test_short_answers_are_still_fact_checked(monkeypatch, voice):
    monkeypatch.setattr(drafts.converse, "fact_check", lambda c, x, d, l: {"claims": [], "corrected": ""})
    out = drafts.draft(Model({"answers": [{"question": "Notice period?", "answer": "Two weeks"}]}),
                       _ctx([{"label": "Notice period?", "required": True, "type": "text"}]), _asset("form_answers"), [])
    assert json.loads(out)[0]["answer"] == "" and voice == []


def test_blank_answers_are_not_fact_checked(monkeypatch, voice):
    called = []
    monkeypatch.setattr(drafts.converse, "fact_check", lambda *a: called.append(a) or {"corrected": ""})
    drafts.draft(Model({"answers": [{"question": "Q", "answer": ""}]}),
                 _ctx([{"label": "Q", "required": True, "type": "text"}]), _asset("form_answers"), [])
    assert called == []


def test_partial_form_revision_is_refused():
    old = json.dumps([{"question": "A", "answer": "1"}, {"question": "B", "answer": "2"}])
    text, note = drafts.revise(Model({"answers": [{"question": "A", "answer": "new"}], "note": "ok"}), _ctx(),
                               _asset("form_answers", old), "x")
    assert text == old and "didn't apply" in note


def test_long_form_answer_is_split_in_code_blocks():
    tg = Tg()
    long = "word " * 1600
    deliver(tg, "42", _ctx(), _asset("form_answers", json.dumps([{"question": "Why?", "answer": long}])))
    assert len(tg.messages) > 1 and all(len(m) <= 4096 for m in tg.messages)
    assert all(m.count("<code>") == 1 and m.count("</code>") == 1 for m in tg.messages)


def test_escaped_entities_are_never_cut():
    tg = Tg()
    deliver(tg, "42", _ctx(), _asset("loom_script", "&" * 9000))
    assert all(m.replace("&amp;", "") == "" for m in tg.messages)
