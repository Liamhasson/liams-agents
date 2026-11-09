"""One Director run, from Brief me to the brief on Telegram (no network, no model)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.director import run as director

PAGE_ID = "407be63a-05ad-8160-bb8f-ed832bc3d9c2"
JID = PAGE_ID.replace("-", "")
POST = "We want someone who ships without a handoff. Record a Loom of your work."
BRIEF = {"after_they_say": ["ships without a handoff"], "after_my_read": "", "candidate_they_say": [],
         "candidate_my_read": "", "why_you": [{"point": "p", "project": "X", "source_quote": "built a tool for bookers"}],
         "weak_spots": []}
ASKS = [{"kind": "loom_or_video", "state": "required", "quote": "Record a Loom of your work"}]


def _text(v):
    return {"type": "rich_text", "rich_text": [{"plain_text": v}]}


def _page(asks=json.dumps(ASKS), source="Ashby:acme", notes="They make rockets."):
    return {"id": PAGE_ID, "properties": {
        "Title": {"type": "title", "title": [{"plain_text": "Designer"}]},
        "Company": _text("Acme"), "Description": _text(POST), "Source": _text(source),
        "Application asks": _text(asks), "Research notes": _text(notes),
        "URL": {"type": "url", "url": "https://jobs.ashbyhq.com/acme/abc"},
        "Status": {"type": "select", "select": {"name": "Approved"}},
    }}


class Notion:
    def __init__(self, page=None):
        self.page, self.updates, self.rows = page or _page(), [], []

    def get_page(self, page_id):
        return self.page

    def update_page(self, page_id, props):
        self.updates.append(props)

    def create_page(self, db, props):
        row = {"id": f"r{len(self.rows)}", "properties": {
            "Job": {"type": "rich_text", "rich_text": [{"plain_text": props["Job"]["rich_text"][0]["text"]["content"]}]},
            "Kind": {"type": "select", "select": props["Kind"]["select"]},
            "State": {"type": "select", "select": props["State"]["select"]},
        }}
        self.rows.append(row)
        return row

    def query_database(self, db, filter=None):
        return self.rows

    def merged(self):
        out = {}
        for u in self.updates:
            out.update(u)
        return out


class Tg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat, text, buttons=None):
        self.sent.append((text, buttons))
        return {"message_id": 77}


class Model:
    calls = 0

    def __init__(self, answer):
        self.answer, self.count = answer, 0

    def json_call(self, *a, **k):
        self.count += 1
        return self.answer


@pytest.fixture(autouse=True)
def _usage(monkeypatch):
    monkeypatch.setattr(director.usage, "over_limit", lambda n: False)
    monkeypatch.setattr(director.usage, "log_run", lambda *a: None)


def _go(notion, tg=None, research=lambda job: {"researched": 1}, sonnet=None, haiku=None, dry_run=False):
    tg = tg or Tg()
    return director.brief_job(PAGE_ID, notion=notion, tg=tg, chat="42", ids={"Assets": "assets"},
                              sonnet=sonnet or Model(BRIEF), haiku=haiku or Model({"application_asks": ASKS}),
                              http=object(), research=research,
                              sources=lambda n: ("I built a tool for bookers.", ""), dry_run=dry_run), tg


def test_run_saves_brief_sets_briefed_and_message_id():
    n = Notion()
    _go(n)
    saved = n.merged()
    assert saved["Status"] == {"select": {"name": "Briefed"}} and saved["Brief message id"] == {"number": 77}
    assert saved["Director brief"]["rich_text"]


def test_brief_goes_to_telegram_with_asset_buttons():
    _, tg = _go(Notion())
    text, buttons = tg.sent[0]
    assert "What they're after" in text and buttons[0][0][1] == f"start:{JID}:loom_script"


def test_assets_are_created():
    n = Notion()
    _go(n)
    assert [r["properties"]["Kind"]["select"]["name"] for r in n.rows] == ["loom_script"]


def test_job_id_without_dashes_still_files_assets_under_the_page_id():
    n = Notion()
    director.brief_job(JID, notion=n, tg=Tg(), chat="42", ids={"Assets": "assets"}, sonnet=Model(BRIEF),
                       haiku=Model({"application_asks": ASKS}), http=object(), research=lambda job: {},
                       sources=lambda x: ("I built a tool for bookers.", ""))
    assert n.rows[0]["properties"]["Job"]["rich_text"][0]["plain_text"] == PAGE_ID


def test_rerun_does_not_duplicate_assets():
    n = Notion()
    _go(n)
    _go(n)
    assert len(n.rows) == 1


def test_director_extracts_asks_for_older_jobs():
    n, haiku = Notion(_page(asks="")), Model({"application_asks": ASKS})
    _go(n, haiku=haiku)
    assert haiku.count == 1 and "Loom" in n.merged()["Application asks"]["rich_text"][0]["text"]["content"]


def test_stored_asks_are_not_extracted_again():
    haiku = Model({"application_asks": ASKS})
    _go(Notion(), haiku=haiku)
    assert haiku.count == 0


def test_other_hiring_tools_say_form_was_not_checked():
    _, tg = _go(Notion())
    assert "Paste" in tg.sent[0][0]


def test_director_failure_tells_liam_and_offers_retry():
    def broken(job):
        raise RuntimeError("research failed")
    n, tg = Notion(), Tg()
    with pytest.raises(RuntimeError):
        _go(n, tg=tg, research=broken)
    text, buttons = tg.sent[0]
    assert "Couldn't" in text and buttons[0][0][1] == f"brief:{JID}"
    assert "Status" not in n.merged()


def test_usage_limit_says_so_on_telegram(monkeypatch):
    monkeypatch.setattr(director.usage, "over_limit", lambda n: True)
    sonnet = Model(BRIEF)
    (result, tg) = _go(Notion(), sonnet=sonnet)
    assert result == {"paused": True} and "limit" in tg.sent[0][0] and sonnet.count == 0


def test_dry_run_writes_and_sends_nothing():
    n = Notion()
    (result, tg) = _go(n, dry_run=True)
    assert n.updates == [] and n.rows == [] and tg.sent == [] and "What they're after" in result["text"]


class FailsOnce(Tg):
    def __init__(self):
        super().__init__()
        self.failed = False

    def send_message(self, chat, text, buttons=None):
        if not self.failed:
            self.failed = True
            raise RuntimeError("Telegram down")
        return super().send_message(chat, text, buttons)


def test_a_failed_send_leaves_no_brief_so_try_again_works():
    n, tg = Notion(), FailsOnce()
    with pytest.raises(RuntimeError):
        _go(n, tg=tg)
    assert "Director brief" not in n.merged() and "Couldn't" in tg.sent[0][0]


def test_long_form_questions_are_stored_whole(monkeypatch):
    form = [{"label": "Q" * 400, "required": True, "type": "text"} for _ in range(40)]
    monkeypatch.setattr(director, "_form", lambda page, http: form)
    n = Notion()
    _go(n)
    stored = "".join(p["text"]["content"] for p in n.merged()["Form questions"]["rich_text"])
    assert json.loads(stored) == form
