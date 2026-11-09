"""The Editor session: answers Liam, closes when idle, and resumes with nothing lost (no network, no model)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.editor import session
from agents.editor.act import Done
from agents.editor.context import EditorContext
from agents.editor.session import Inbox, log_out, restore_history
from shared.assets import Asset

JOB = "407be63a-05ad-8160-bb8f-ed832bc3d9c2"
JID = JOB.replace("-", "")


def _rt(v):
    return {"type": "rich_text", "rich_text": [{"plain_text": v}]}


def _row(text, read=False, direction="in", update=1, at="2026-11-09T10:00:00+00:00", pid=None):
    return {"id": pid or f"row-{text}", "properties": {
        "Text": {"type": "title", "title": [{"plain_text": text[:100]}]}, "Full text": _rt(text), "Job": _rt(JOB),
        "Read": {"type": "checkbox", "checkbox": read},
        "Telegram update id": {"type": "number", "number": update},
        "Received at": {"type": "date", "date": {"start": at}},
        "Direction": {"type": "select", "select": {"name": direction}},
    }}


class InboxNotion:
    def __init__(self, rows):
        self.rows, self.read, self.created = rows, [], []

    def query_database(self, db, filter=None):
        unread_only = "Read" in str(filter)
        return [r for r in self.rows if not (unread_only and r["properties"]["Read"]["checkbox"])]

    def update_page(self, page_id, props):
        self.read.append(page_id)
        next(r for r in self.rows if r["id"] == page_id)["properties"]["Read"]["checkbox"] = True

    def create_page(self, db, props):
        self.created.append(props)
        return {"id": "out"}


def test_inbox_returns_unread_oldest_first_and_does_not_mark_them():
    n = InboxNotion([_row("second", update=2), _row("first", update=1)])
    box = Inbox(n, "inbox", JOB)
    rows = box.wait(0)
    assert [box.text(r) for r in rows] == ["first", "second"] and n.read == []


def test_mark_read_stops_a_row_coming_back():
    n = InboxNotion([_row("hi")])
    box = Inbox(n, "inbox", JOB)
    box.mark_read(box.wait(0)[0])
    assert box.wait(0) == []


def test_both_sides_are_logged_and_history_restores():
    n = InboxNotion([_row("make it short", read=True, at="2026-11-09T10:00:00+00:00"),
                     _row("Done that.", read=True, direction="out", at="2026-11-09T10:00:30.500000+00:00"),
                     _row("not read yet", at="2026-11-09T10:01:00+00:00")])
    assert restore_history(n, "inbox", JOB) == [{"role": "user", "content": "make it short"},
                                                {"role": "assistant", "content": "Done that."}]


def test_log_out_saves_a_read_outgoing_row():
    n = InboxNotion([])
    log_out(n, "inbox", JOB, "Here's your CV.")
    props = n.created[0]
    assert props["Direction"] == {"select": {"name": "out"}} and props["Read"] == {"checkbox": True}


class FakeInbox:
    """Each wait hands over the next batch."""

    def __init__(self, batches):
        self.batches, self.read = list(batches), []

    def wait(self, seconds):
        return self.batches.pop(0) if self.batches else []

    def text(self, row):
        return row

    def mark_read(self, row):
        self.read.append(row)


class Notion:
    def __init__(self, status="Briefed"):
        self.status, self.windows, self.updates, self.logged = status, [], [], []

    def ensure_databases(self):
        return {"Jobs": "jobs", "Inbox": "inbox", "Assets": "assets"}

    def get_page(self, page_id):
        return {"id": JOB, "properties": {"Status": {"type": "select", "select": {"name": self.status}}}}

    def update_page(self, page_id, props):
        if "Session until" in props:
            self.windows.append(props["Session until"]["date"])
        else:
            self.updates.append(props)

    def create_page(self, db, props):
        self.logged.append(props["Full text"]["rich_text"][0]["text"]["content"])
        return {"id": "x"}

    def query_database(self, db, filter=None):
        return []


class Tg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat, text, buttons=None):
        self.sent.append((text, buttons))
        return {"message_id": 1}


def _ctx():
    return EditorContext(JOB, "Designer", "Acme", "Berlin", "product design", "", "", "", "https://acme.com/1", "", "")


def _assets(state="needed", text=""):
    return [Asset("row", JOB, "cv", state, "CV", "", text, text)]


@pytest.fixture
def go(monkeypatch):
    def run(batches, *, status="Briefed", assets=None, turn=None, actions=None, job=JOB, context=None, loader=None, **kw):
        n, tg, box = Notion(status), Tg(), FakeInbox(batches)
        seen = {"assets": [], "history": []}
        clock = [datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)]

        def _now():
            clock[0] += timedelta(seconds=30)
            return clock[0]

        def _turn(claude, ctx, history, current):
            seen["assets"].append(list(current))
            seen["history"].append(list(history))
            return turn(history) if turn else {"reply": "On it.", "actions": []}

        monkeypatch.setattr(session, "_now", _now)
        monkeypatch.setattr(session, "NotionClient", lambda: n)
        monkeypatch.setattr(session, "Telegram", lambda: tg)
        monkeypatch.setattr(session, "Claude", lambda model=None: object())
        monkeypatch.setattr(session.config, "require", lambda key: "42")
        monkeypatch.setattr(session.ctxmod, "build_context", context or (lambda notion, page: _ctx()))
        def _open(notion, ids, opened):
            seen["job"] = opened
            return box

        monkeypatch.setattr(session, "_open_inbox", _open)
        monkeypatch.setattr(session, "load_assets", lambda notion, db, job: loader() if loader else (assets if assets is not None else _assets()))
        monkeypatch.setattr(session, "restore_history", kw.pop("restore", lambda notion, db, job: []))
        monkeypatch.setattr(session.usage, "log_run", lambda *a: None)
        monkeypatch.setattr(session, "turn", _turn)
        monkeypatch.setattr(session, "apply_actions", actions or (lambda env, a, m: Done()))
        result = session.run(job, idle_minutes=0, **kw)
        return result, n, tg, box, seen
    return run


def test_message_that_started_session_is_answered_first(go):
    _, n, tg, box, seen = go([["first text"]])
    assert tg.sent[0][0] == "On it." and box.read == ["first text"]
    assert seen["history"][0][-1] == {"role": "user", "content": "first text"}


def test_replies_are_logged(go):
    _, n, *_ = go([["hello"]])
    assert n.logged == ["On it."]


def test_window_rolls_forward_with_each_message(go):
    _, n, *_ = go([["one"], ["two"]])
    live = [w["start"] for w in n.windows if w]
    assert len(live) == 2 and live[0] < live[1]


def test_closes_after_idle_and_clears_window(go):
    result, n, tg, *_ = go([["hello"]])
    assert n.windows[-1] is None and result == {"closed": True}
    assert "Text me" in tg.sent[-1][0]


def test_final_check_catches_a_last_second_message(go):
    _, n, tg, box, _ = go([["first"], [], ["just in time"]])
    assert box.read == ["first", "just in time"]


def test_resume_keeps_drafts_and_history(go):
    earlier = lambda notion, db, job: [{"role": "user", "content": "before"}]
    _, _, _, _, seen = go([["again"]], assets=_assets("drafted", "my saved cv"), restore=earlier)
    assert seen["assets"][0][0].text == "my saved cv"
    assert seen["history"][0][0] == {"role": "user", "content": "before"}


def test_crash_leaves_unread_messages_for_next_run(go):
    def bad(history):
        raise RuntimeError("model down")
    with pytest.raises(RuntimeError):
        go([["lost?"]], turn=bad)
    assert session.NotionClient().windows[-1] is None
    assert session._open_inbox(None, None, JOB).read == []
    assert "Nothing is lost" in session.Telegram().sent[-1][0]


def test_status_becomes_drafting_when_briefed(go):
    _, n, *_ = go([["hi"]])
    assert n.updates[0] == {"Status": {"select": {"name": "Drafting"}}}


def test_status_is_left_alone_on_a_job_already_applied(go):
    _, n, *_ = go([["hi"]], status="Applied")
    assert n.updates == []


def test_drop_ends_the_session_quietly(go):
    result, n, tg, box, _ = go([["drop it"], ["ignored"]], actions=lambda e, a, m: Done(dropped=True))
    assert result == {"dropped": True} and box.read == ["drop it"] and n.windows[-1] is None
    assert not any("Text me" in t for t, _ in tg.sent)


def test_all_assets_done_sends_checklist_once(go):
    assets = _assets("drafted", "cv text")

    def finish(env, a, m):
        env.assets[0] = Asset("row", JOB, "cv", "final", "CV", "", "cv text", "cv text")
        return Done(lines=["CV is final."])

    _, n, tg, *_ = go([["final"], ["thanks"]], assets=assets, actions=finish)
    lists = [(t, b) for t, b in tg.sent if "Before you apply" in t]
    assert len(lists) == 1 and "https://acme.com/1" in lists[0][0]
    assert lists[0][1] == [[("✅ Applied", f"applied:{JID}")]]
    assert {"Status": {"select": {"name": "Ready to send"}}} in n.updates


def test_stops_at_the_time_limit_and_keeps_the_rest_unread(go):
    result, _, tg, box, _ = go([["one"], ["two"]], max_minutes=0)
    assert result == {"closed": True} and box.read == ["one"] and "Text me" in tg.sent[-1][0]


def test_job_id_without_dashes_is_normalised(go):
    *_, seen = go([["hi"]], job=JID)
    assert seen["job"] == JOB


def test_html_in_replies_is_escaped(go):
    _, _, tg, *_ = go([["hi"]], turn=lambda h: {"reply": "a < b", "actions": []})
    assert tg.sent[0][0] == "a &lt; b"


def test_actions_receive_the_message(go):
    got = []
    go([["make it short"]], turn=lambda h: {"reply": "ok", "actions": [{"type": "x"}]},
       actions=lambda e, a, m: (got.append((a, m)), Done())[1])
    assert got == [([{"type": "x"}], "make it short")]


def test_checklist_lists_finals_skips_and_link():
    ctx = _ctx()
    env = session.Env(notion=None, tg=None, chat="42", claude=None, ctx=ctx, ids={}, assets=[
        Asset("a", JOB, "cv", "final", "CV", "", "x", "x"), Asset("b", JOB, "cover_letter", "skipped", "Cover letter", "", "", ""),
        Asset("c", JOB, "portfolio", "needed", "Portfolio link", "", "", "")])
    text, _ = session.checklist(env)
    assert "CV: Ready" in text and "Cover letter: Skipped" in text and "Portfolio link: Yours to handle" in text
    assert "https://acme.com/1" in text


def test_a_run_with_nothing_to_answer_exits_silently(go):
    result, n, tg, *_ = go([])
    assert result == {"nothing": True} and tg.sent == [] and n.updates == [] and n.windows[-1] is None


def test_window_rolls_when_a_message_is_picked_up_before_the_work(go):
    marks = []

    def slow(history):
        marks.append(len(session.NotionClient().windows))
        return {"reply": "ok", "actions": []}

    go([["one"], ["two"]], turn=slow)
    assert marks[0] == 1 and marks[1] == 2


def test_window_clears_before_the_last_look(go):
    _, n, *_ = go([["one"], [], ["late"]])
    assert None in n.windows[:-1]


def test_start_up_failure_is_reported(monkeypatch, go):
    def broken(notion, page):
        raise ValueError("bad form json")

    with pytest.raises(ValueError):
        go([["hi"]], context=broken)
    assert "Nothing is lost" in session.Telegram().sent[-1][0]


def test_status_goes_back_to_drafting_when_a_final_asset_reopens(go):
    done = [Asset("row", JOB, "cv", "final", "CV", "", "t", "t")]

    def reopen(env, a, m):
        env.assets[0] = Asset("row", JOB, "cv", "drafted", "CV", "", "t2", "t")
        return Done()

    _, n, *_ = go([["change it"]], status="Ready to send", assets=done, actions=reopen)
    assert {"Status": {"select": {"name": "Drafting"}}} in n.updates


def test_assets_are_reloaded_each_turn(go, monkeypatch):
    loads = [_assets("needed"), [Asset("row", JOB, "cv", "skipped", "CV", "", "", "")],
             [Asset("row", JOB, "cv", "skipped", "CV", "", "", "")]]
    def next_load():
        return loads.pop(0) if len(loads) > 1 else loads[0]
    *_, seen = go([["after skip"]], loader=next_load)
    assert seen["assets"][0][0].state == "skipped"
