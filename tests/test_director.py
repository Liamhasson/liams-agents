"""The Director's form lookup, asset plan and brief (no network, no model)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.director.brief import brief_message, plan_assets, verified_brief
from agents.director.forms import greenhouse_questions, parse_greenhouse
from shared.assets import Planned

JID = "407be63a05ad8160bb8fed832bc3d9c2"
BRIEF = {
    "after_they_say": ["Own the onboarding flow end to end"],
    "after_my_read": "They probably lost people at sign-up.",
    "candidate_they_say": ["ships without a handoff"],
    "candidate_my_read": "",
    "why_you": [{"point": "You built a tool alone", "project": "Project X",
                 "source_quote": "built a tool for bookers"}],
    "weak_spots": ["They ask for mobile work and you have little to show"],
}
POST = "You will own the onboarding flow end to end. We want someone who ships without a handoff."


class _Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class _Client:
    def __init__(self, data=None, fail=False):
        self.data, self.fail, self.urls = data, fail, []

    def get(self, url):
        self.urls.append(url)
        if self.fail:
            raise RuntimeError("404")
        return _Resp(self.data)


def _q(label, required=False, kind="input_text"):
    return {"label": label, "required": required, "fields": [{"type": kind}]}


def test_parse_greenhouse_from_board_url():
    assert parse_greenhouse("Greenhouse:acme", "https://job-boards.greenhouse.io/acme/jobs/123") == ("acme", "123")


def test_parse_greenhouse_from_company_url():
    assert parse_greenhouse("Greenhouse:acme", "https://acme.com/careers/1?gh_jid=456") == ("acme", "456")


def test_other_tools_are_not_greenhouse():
    assert parse_greenhouse("Ashby:acme", "https://jobs.ashbyhq.com/acme/abc") is None


def test_form_skips_identity_fields():
    client = _Client({"questions": [_q("First Name", True), _q("Last Name", True), _q("Email", True),
                                    _q("Phone"), _q("Why us?", True, "textarea")]})
    assert greenhouse_questions(client, "acme", "1") == [{"label": "Why us?", "required": True, "type": "textarea"}]
    assert "questions=true" in client.urls[0]


def test_form_cleans_divider_lines_from_labels():
    client = _Client({"questions": [_q("_______\nWhat is your notice period?"), _q("______")]})
    assert [q["label"] for q in greenhouse_questions(client, "a", "1")] == ["What is your notice period?"]


def test_closed_post_returns_none():
    assert greenhouse_questions(_Client(fail=True), "acme", "1") is None


def _ask(kind, state):
    return {"kind": kind, "state": state, "quote": "the post's words"}


def test_plan_loom_needed_cv_optional_not_listed_when_not_wanted():
    p = plan_assets([_ask("loom_or_video", "required"), _ask("cv", "not_wanted")], None)
    assert [(a.kind, a.state) for a in p] == [("loom_script", "needed")]


def test_plan_keeps_the_posts_words():
    assert plan_assets([_ask("cv", "required")], None)[0].quote == "the post's words"


def test_plan_form_overrides_post_for_required_and_optional():
    form = [{"label": "Resume/CV", "required": True, "type": "input_file"},
            {"label": "Cover Letter", "required": False, "type": "input_file"}]
    p = plan_assets([_ask("cv", "optional"), _ask("cover_letter", "required")], form)
    assert {(a.kind, a.state) for a in p} == {("cv", "needed"), ("cover_letter", "optional")}


def test_plan_post_refusal_beats_an_optional_upload_field():
    form = [{"label": "Cover Letter", "required": False, "type": "input_file"}]
    assert plan_assets([_ask("cover_letter", "not_wanted")], form) == []


def test_plan_custom_questions_make_form_answers():
    form = [{"label": "Why us?", "required": True, "type": "textarea"}]
    assert [(a.kind, a.state) for a in plan_assets([], form)] == [("form_answers", "needed")]


def test_plan_portfolio_and_linkedin_fields_are_checklist_items():
    form = [{"label": "Please add a link to your portfolio", "required": True, "type": "input_text"},
            {"label": "LinkedIn, website or other links", "required": False, "type": "textarea"}]
    assert {(a.kind, a.state) for a in plan_assets([], form)} == {("portfolio", "needed"), ("linkedin", "optional")}


def test_plan_nothing_stated_offers_cv_and_letter_as_optional():
    assert {(a.kind, a.state) for a in plan_assets([], None)} == {("cv", "optional"), ("cover_letter", "optional")}


def test_plan_lists_drafted_assets_first():
    p = plan_assets([_ask("portfolio", "required"), _ask("loom_or_video", "required")], None)
    assert [a.kind for a in p] == ["loom_script", "portfolio"]


def test_why_point_with_failed_quote_is_dropped():
    b = verified_brief({**BRIEF, "why_you": [
        {"point": "a", "project": "X", "source_quote": "built a tool for bookers"},
        {"point": "b", "project": "Y", "source_quote": "led a team of forty people"}]},
        cv="I built a tool for bookers.", mytone="")
    assert [p["point"] for p in b["why_you"]] == ["a"]


def test_why_quote_can_come_from_mytone():
    assert verified_brief(BRIEF, cv="", mytone="He built a tool for bookers alone.")["why_you"]


def test_they_say_quotes_must_be_in_the_post():
    b = verified_brief({**BRIEF, "after_they_say": ["Own the onboarding flow end to end", "Fluent in Rust and Go"]},
                       cv="built a tool for bookers", mytone="", post=POST)
    assert b["after_they_say"] == ["Own the onboarding flow end to end"]


def _msg(brief=BRIEF, planned=None, form_checked=True):
    planned = planned if planned is not None else [Planned("cv", "needed", "CV", "q"),
                                                   Planned("portfolio", "needed", "Portfolio link", "q")]
    return brief_message(brief, planned, form_checked, JID, "Designer", "Acme")


def test_message_separates_they_say_and_my_read():
    text = _msg()[0]
    assert "They say" in text and "My read" in text
    assert text.index("Own the onboarding") < text.index("They probably lost")


def test_message_leaves_out_an_empty_read():
    assert _msg()[0].count("My read") == 1


def test_message_names_the_project_behind_each_point():
    assert "You built a tool alone" in _msg()[0] and "Project X" in _msg()[0]


def test_message_shows_weak_spots():
    assert "little to show" in _msg()[0]


def test_message_has_start_and_skip_for_each_drafted_asset():
    datas = [d for row in _msg()[1] for _, d in row]
    assert f"start:{JID}:cv" in datas and f"skipasset:{JID}:cv" in datas


def test_checklist_items_have_no_buttons():
    assert not any("portfolio" in d for row in _msg()[1] for _, d in row)
    assert "Portfolio link" in _msg()[0]


def test_callback_data_fits_telegram():
    planned = [Planned("cover_letter", "needed", "Cover letter", ""), Planned("form_answers", "needed", "Form", "")]
    assert all(len(d.encode()) <= 64 for row in _msg(planned=planned)[1] for _, d in row)


def test_message_asks_to_paste_when_form_not_checked():
    assert "Paste" in _msg(form_checked=False)[0]
    assert "Paste" not in _msg(form_checked=True)[0]


def test_message_asks_where_to_start():
    assert "Where do you want to start?" in _msg()[0]


def test_message_says_when_the_post_does_not_say():
    planned = [Planned("cv", "optional", "CV", ""), Planned("cover_letter", "optional", "Cover letter", "")]
    assert "doesn't say what to send" in _msg(planned=planned)[0]


def test_message_escapes_html():
    assert "&lt;b&gt;" in _msg(brief={**BRIEF, "after_my_read": "<b>bold</b>"})[0]


def test_a_normal_length_read_is_not_cut_off():
    read = "They want someone who already builds with these tools every day. " * 5
    assert read.strip() in _msg(brief={**BRIEF, "after_my_read": read})[0]


def test_apostrophes_stay_readable():
    assert "don't" in _msg(brief={**BRIEF, "after_my_read": "They don't know yet."})[0]


def test_message_fits_one_telegram_message():
    huge = "word " * 2000
    b = {"after_they_say": [huge] * 5, "after_my_read": huge, "candidate_they_say": [huge] * 5,
         "candidate_my_read": huge, "why_you": [{"point": huge, "project": huge, "source_quote": "q"}] * 8,
         "weak_spots": [huge] * 6}
    assert len(_msg(brief=b)[0]) < 4096


def test_a_post_with_only_checklist_items_offers_applied():
    planned = [Planned("portfolio", "needed", "Portfolio link", "q")]
    assert _msg(planned=planned)[1] == [[("✅ Applied", f"applied:{JID}")]]


def test_rejected_lines_in_the_guide_cannot_prove_a_point():
    guide = '[Acme, CV, 2026-11-09] Instead of "built a tool for bookers", Liam wrote "made a thing".'
    assert verified_brief(BRIEF, cv="", mytone=guide)["why_you"] == []
