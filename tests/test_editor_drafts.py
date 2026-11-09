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
