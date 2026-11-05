"""Tests for answering Telegram taps and messages (webhook + backup poller). No network."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.messenger import handle
from agents.messenger.handle import handle_update

CHAT = "42"
IDS = {"Jobs": "jobs", "Inbox": "inbox"}
JID = "407be63a05ad8160bb8fed832bc3d9c2"
PAGE_ID = "407be63a-05ad-8160-bb8f-ed832bc3d9c2"


def _page(status="Asked Liam", title="Product Designer", cv=""):
    return {"id": PAGE_ID, "properties": {
        "Title": {"type": "title", "title": [{"plain_text": title}]},
        "Status": {"type": "select", "select": {"name": status}},
        "CV draft": {"type": "rich_text", "rich_text": [{"plain_text": cv}] if cv else []},
        "Description": {"type": "rich_text", "rich_text": [{"plain_text": "Design things."}]},
        "URL": {"type": "url", "url": "https://acme.com/jobs/1"},
    }}


class FakeTelegram:
    def __init__(self):
        self.sent, self.answered = [], []

    def send_message(self, chat, text, buttons=None):
        self.sent.append((text, buttons))

    def answer_callback(self, qid, text=""):
        self.answered.append(qid)


class FakeNotion:
    """Jobs + Inbox in memory. `live` = the job a Writer session is running for."""

    def __init__(self, page=None, live=None, card_for=None, waiting=()):
        self.page, self.live, self.card_for, self.waiting = page or _page(), live, card_for, list(waiting)
        self.updates, self.created, self.open_jobs = [], [], []

    def get_page(self, page_id):
        assert page_id == PAGE_ID
        return self.page

    def update_page(self, page_id, props):
        self.updates.append(props)
        if "Status" in props:
            self.page["properties"]["Status"]["select"]["name"] = props["Status"]["select"]["name"]

    def create_page(self, db, props):
        self.created.append((db, props))

    def query_database(self, db, filter=None):
        if filter.get("property") == "Session until":
            return [self.live] if self.live else []
        if filter.get("property") == "Telegram message id":
            return [self.page] if filter["number"]["equals"] == self.card_for else []
        if "Score" in str(filter):
            self.last_jobs_filter = filter
            return list(self.open_jobs)
        return self.waiting  # Approved + no CV draft


def tap(data, chat=CHAT):
    return {"update_id": 7, "callback_query": {"id": "q1", "data": data, "message": {"chat": {"id": chat}}}}


def msg(text, chat=CHAT, reply_to=None):
    m = {"chat": {"id": chat}, "text": text}
    if reply_to:
        m["reply_to_message"] = {"message_id": reply_to}
    return {"update_id": 9, "message": m}


def run(update, notion, start=lambda job: None):
    tg = FakeTelegram()
    started = []

    def _start(job):
        started.append(job)
        return start(job)

    label = handle_update(update, tg, notion, IDS, CHAT, start=_start)
    return label, tg, started


def test_apply_tap_approves_confirms_and_starts_writer():
    notion = FakeNotion()
    label, tg, started = run(tap(f"apply:{JID}"), notion)
    assert label == "writer-started"
    assert notion.page["properties"]["Status"]["select"]["name"] == "Approved"
    assert tg.answered == ["q1"]  # spinner stopped
    assert started == [JID]
    texts = [t for t, _ in tg.sent]
    assert "Approved" in texts[0] and "Product Designer" in texts[0]
    assert "few minutes" in texts[1]


def test_writer_that_fails_to_start_tells_liam_why():
    notion = FakeNotion()
    label, tg, _ = run(tap(f"apply:{JID}"), notion, start=lambda job: "GitHub said 403: Bad credentials")
    assert label == "writer-failed"
    assert "Couldn't start the Writer" in tg.sent[-1][0] and "403" in tg.sent[-1][0]


def test_second_apply_tap_says_already_handled_and_starts_nothing():
    label, tg, started = run(tap(f"apply:{JID}"), FakeNotion(_page(status="Approved")))
    assert label == "already" and started == []
    assert "already handled" in tg.sent[0][0]


def test_skip_tap():
    notion = FakeNotion()
    label, tg, started = run(tap(f"skip:{JID}"), notion)
    assert label == "skipped" and started == []
    assert notion.page["properties"]["Status"]["select"]["name"] == "Skipped"


def test_more_tap_sends_details():
    label, tg, _ = run(tap(f"more:{JID}"), FakeNotion())
    assert label == "more" and "Design things." in tg.sent[0][0]


def test_tap_from_another_chat_is_refused():
    notion = FakeNotion()
    label, tg, started = run(tap(f"apply:{JID}", chat="999"), notion)
    assert label == "not-mine" and started == [] and notion.updates == [] and tg.sent == []


def test_apply_while_writing_another_job_says_it_will_follow():
    live = {"id": "other-job"}
    label, tg, started = run(tap(f"apply:{JID}"), FakeNotion(live=live))
    assert label == "writer-started" and started == [JID]
    assert "as soon as the current write-up is done" in tg.sent[-1][0]


def test_message_during_live_session_goes_to_inbox():
    notion = FakeNotion(live={"id": "job-live"})
    label, tg, _ = run(msg("Make the opening shorter"), notion)
    assert label == "inbox" and tg.sent == []
    db, props = notion.created[0]
    assert db == "inbox"
    assert props["Full text"]["rich_text"][0]["text"]["content"] == "Make the opening shorter"
    assert props["Job"]["rich_text"][0]["text"]["content"] == "job-live"
    assert props["Read"] == {"checkbox": False}


def test_reply_apply_to_job_card_approves_and_starts_writer():
    notion = FakeNotion(card_for=555)
    label, tg, started = run(msg("apply", reply_to=555), notion)
    assert label == "writer-started" and started == [JID]


def test_reply_apply_to_job_card_mid_session_is_still_a_decision():
    notion = FakeNotion(card_for=555, live={"id": "other-job"})
    label, _, started = run(msg("skip", reply_to=555), notion)
    assert label == "skipped" and notion.created == []


def test_unknown_text_gets_help_and_resume_buttons():
    waiting = [_page(status="Approved", title="Brand Designer")]
    label, tg, _ = run(msg("what's going on?"), FakeNotion(waiting=waiting))
    assert label == "help"
    text, buttons = tg.sent[0]
    assert "didn't catch that" in text
    assert buttons == [[("▶️ Write: Brand Designer", f"resume:{JID}")]]


def test_unknown_text_with_nothing_waiting_still_gets_a_reply():
    label, tg, _ = run(msg("hello?"), FakeNotion())
    assert label == "help" and tg.sent and tg.sent[0][1] is None


def test_greeting():
    label, tg, _ = run(msg("/start"), FakeNotion())
    assert label == "greeting" and "Hi Liam" in tg.sent[0][0]


def test_resume_tap_starts_writer_for_approved_job():
    label, tg, started = run(tap(f"resume:{JID}"), FakeNotion(_page(status="Approved")))
    assert label == "writer-started" and started == [JID]


def test_resume_tap_for_already_written_job_does_nothing():
    label, tg, started = run(tap(f"resume:{JID}"), FakeNotion(_page(status="Approved", cv="# CV")))
    assert label == "already" and started == []


def test_start_writer_without_token_explains():
    import os
    saved = os.environ.pop("GITHUB_DISPATCH_TOKEN", None)
    try:
        assert handle.start_writer("x") == "GITHUB_DISPATCH_TOKEN is not set"
    finally:
        if saved is not None:
            os.environ["GITHUB_DISPATCH_TOKEN"] = saved


def test_webhook_rejects_wrong_or_missing_secret():
    import os
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "api" / "telegram.py"
    spec = importlib.util.spec_from_file_location("api_telegram", path)
    tgmod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tgmod)
    saved = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "s3cret"
    try:
        assert tgmod.authorised("s3cret")
        assert not tgmod.authorised("wrong")
        assert not tgmod.authorised(None)
        os.environ["TELEGRAM_WEBHOOK_SECRET"] = ""
        assert not tgmod.authorised("")  # no secret configured → refuse everything
    finally:
        if saved is None:
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
        else:
            os.environ["TELEGRAM_WEBHOOK_SECRET"] = saved


def _scored(title, score, company="Acme"):
    p = _page(title=title)
    p["properties"]["Score"] = {"type": "number", "number": score}
    p["properties"]["Company"] = {"type": "rich_text", "rich_text": [{"plain_text": company}]}
    return p


def test_jobs_command_lists_open_matches_best_first_with_buttons():
    notion = FakeNotion()
    notion.open_jobs = [_scored("Designer A", 72), _scored("Designer B", 88, "Linear")]
    label, tg, _ = run(msg("jobs"), notion)
    assert label == "jobs"
    text, buttons = tg.sent[0]
    assert text.index("Designer B") < text.index("Designer A") and "88" in text and "Linear" in text
    assert buttons[0] == [("✅ Apply 1", f"apply:{JID}"), ("ℹ️ More 1", f"more:{JID}")]
    want = handle.alert_threshold()  # the Matcher's strong-match score from settings.yaml
    assert f"'greater_than_or_equal_to': {want}" in str(notion.last_jobs_filter)


def test_jobs_with_a_number_uses_that_score_and_works_mid_session():
    notion = FakeNotion(live={"id": "job-live"})
    label, tg, _ = run(msg("Jobs 55"), notion)
    assert label == "jobs-none" and notion.created == []  # not sent to the Writer's inbox
    assert "55" in tg.sent[0][0] and "jobs 35" in tg.sent[0][0]
