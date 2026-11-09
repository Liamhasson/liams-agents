"""Tests for answering Telegram taps and messages (webhook + backup poller). No network."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.messenger import handle
from agents.messenger.handle import handle_update

CHAT = "42"
IDS = {"Jobs": "jobs", "Inbox": "inbox", "Assets": "assets"}
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

    def __init__(self, page=None, live=None, card_for=None, waiting=(), ready=(), brief_for=None, orphans=()):
        self.page, self.live, self.card_for, self.waiting = page or _page(), live, card_for, list(waiting)
        self.ready, self.brief_for, self.orphans = list(ready), brief_for, list(orphans)
        self.updates, self.created, self.open_jobs, self.windows = [], [], [], []
        self.asset_rows = [{"id": "row-cv", "properties": {
            "Job": {"type": "rich_text", "rich_text": [{"plain_text": PAGE_ID}]},
            "Kind": {"type": "select", "select": {"name": "cv"}},
            "State": {"type": "select", "select": {"name": "needed"}},
            "Label": {"type": "rich_text", "rich_text": [{"plain_text": "CV"}]}}}]

    def get_page(self, page_id):
        assert page_id == PAGE_ID
        return self.page

    def update_page(self, page_id, props):
        self.updates.append(props)
        if "Session until" in props:
            self.windows.append(props["Session until"]["date"])
        if "Status" in props:
            self.page["properties"]["Status"]["select"]["name"] = props["Status"]["select"]["name"]

    def create_page(self, db, props):
        self.created.append((db, props))

    def query_database(self, db, filter=None):
        if filter.get("property") == "Session until":
            return [self.live] if self.live else []
        if filter.get("property") == "Brief message id":
            return [self.page] if filter["number"]["equals"] == self.brief_for else []
        if filter.get("property") == "Job":
            return self.asset_rows
        if "is_empty" in str(filter) and "Read" in str(filter):
            return self.orphans
        if "Briefed" in str(filter):
            return self.ready
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


def run(update, notion, start=lambda job: None, editor=lambda job: None):
    tg = FakeTelegram()
    started = []
    notion.editor_started = []

    def _start(job):
        started.append(job)
        return start(job)

    def _editor(job):
        notion.editor_started.append(job)
        return editor(job)

    label = handle_update(update, tg, notion, IDS, CHAT, start_director=_start, start_editor=_editor)
    return label, tg, started


def test_brief_me_tap_approves_and_starts_director():
    notion = FakeNotion()
    label, tg, started = run(tap(f"apply:{JID}"), notion)
    assert label == "director-started"
    assert notion.page["properties"]["Status"]["select"]["name"] == "Approved"
    assert tg.answered == ["q1"]  # spinner stopped
    assert started == [JID]
    texts = [t for t, _ in tg.sent]
    assert "Approved" in texts[0] and "Product Designer" in texts[0]
    assert "couple of minutes" in texts[1]


def test_director_that_fails_to_start_tells_liam_why():
    notion = FakeNotion()
    label, tg, _ = run(tap(f"apply:{JID}"), notion, start=lambda job: "GitHub said 403: Bad credentials")
    assert label == "director-failed"
    assert "Couldn't start the Director" in tg.sent[-1][0] and "403" in tg.sent[-1][0]


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


def test_brief_me_works_during_another_chat():
    live = {"id": "other-job"}
    label, tg, started = run(tap(f"apply:{JID}"), FakeNotion(live=live))
    assert label == "director-started" and started == [JID]


def test_old_apply_and_yes_buttons_still_work():
    assert run(tap(f"yes:{JID}"), FakeNotion())[0] == "director-started"
    assert run(tap(f"apply:{JID}"), FakeNotion())[0] == "director-started"


def test_retry_button_restarts_a_failed_brief():
    label, _, started = run(tap(f"brief:{JID}"), FakeNotion(_page(status="Approved")))
    assert label == "director-started" and started == [JID]


def test_message_during_live_session_goes_to_inbox():
    notion = FakeNotion(live={"id": "job-live"})
    label, tg, _ = run(msg("Make the opening shorter"), notion)
    assert label == "inbox" and tg.sent == []
    db, props = notion.created[0]
    assert db == "inbox"
    assert props["Full text"]["rich_text"][0]["text"]["content"] == "Make the opening shorter"
    assert props["Job"]["rich_text"][0]["text"]["content"] == "job-live"
    assert props["Read"] == {"checkbox": False}


def test_reply_apply_to_job_card_starts_director():
    notion = FakeNotion(card_for=555)
    label, tg, started = run(msg("apply", reply_to=555), notion)
    assert label == "director-started" and started == [JID]


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
    assert buttons == [[("▶️ Brief me: Brand Designer", f"resume:{JID}")]]


def test_unknown_text_with_nothing_waiting_still_gets_a_reply():
    label, tg, _ = run(msg("hello?"), FakeNotion())
    assert label == "help" and tg.sent and tg.sent[0][1] is None


def test_greeting():
    label, tg, _ = run(msg("/start"), FakeNotion())
    assert label == "greeting" and "Hi Liam" in tg.sent[0][0]


def test_resume_tap_briefs_an_approved_job():
    label, tg, started = run(tap(f"resume:{JID}"), FakeNotion(_page(status="Approved")))
    assert label == "director-started" and started == [JID]


def test_resume_tap_for_an_already_briefed_job_does_nothing():
    label, tg, started = run(tap(f"resume:{JID}"), FakeNotion(_page(status="Briefed")))
    assert label == "already" and started == []


def test_start_director_without_token_explains():
    import os
    saved = os.environ.pop("GITHUB_DISPATCH_TOKEN", None)
    try:
        assert handle.start_director("x") == "GITHUB_DISPATCH_TOKEN is not set"
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
    assert buttons[0] == [("✅ Brief 1", f"apply:{JID}"), ("ℹ️ More 1", f"more:{JID}")]
    want = handle.alert_threshold()  # the Matcher's strong-match score from settings.yaml
    assert f"'greater_than_or_equal_to': {want}" in str(notion.last_jobs_filter)


def test_jobs_with_a_number_uses_that_score_and_works_mid_session():
    notion = FakeNotion(live={"id": "job-live"})
    label, tg, _ = run(msg("Jobs 55"), notion)
    assert label == "jobs-none" and notion.created == []  # not sent to the Writer's inbox
    assert "55" in tg.sent[0][0] and "jobs 35" in tg.sent[0][0]


def test_skip_offers_optional_reasons():
    notion = FakeNotion()
    label, tg, _ = run(tap(f"skip:{JID}"), notion)
    datas = [d for row in tg.sent[0][1] for _, d in row]
    assert label == "skipped" and f"why:{JID}:senior" in datas and f"why:{JID}:ad" in datas


def test_skip_reason_tap_is_recorded():
    notion = FakeNotion()
    label, tg, started = run(tap(f"why:{JID}:senior"), notion)
    assert label == "why" and started == [] and tg.sent == []
    assert notion.updates[-1] == {"Skip reason": {"select": {"name": "too senior"}}}


def test_unknown_skip_reason_is_ignored():
    notion = FakeNotion()
    assert run(tap(f"why:{JID}:nonsense"), notion)[0] == "ignored" and notion.updates == []


def _with_fit(page, fit):
    page["properties"]["Fit score"] = {"type": "number", "number": fit}
    page["properties"]["Score"] = {"type": "number", "number": 80}
    return page


def test_jobs_list_hides_fit_below_50_keeps_unscored_legacy():
    notion = FakeNotion()
    low, ok, legacy = _page(title="Low"), _page(title="Good"), _page(title="Legacy")
    _with_fit(low, 42), _with_fit(ok, 72)
    legacy["properties"]["Score"] = {"type": "number", "number": 60}
    notion.open_jobs = [low, ok, legacy]
    _, tg, _ = run(msg("jobs 40"), notion)
    assert "Good" in tg.sent[0][0] and "Legacy" in tg.sent[0][0] and "Low" not in tg.sent[0][0]
    assert "Fit 72" in tg.sent[0][0]


def _ready(status="Briefed", title="Designer", pid=PAGE_ID):
    p = _page(status=status, title=title)
    p["id"] = pid
    return p


OTHER_ID = "11111111-05ad-8160-bb8f-ed832bc3d9c2"


def _inbox_text(notion, i=0):
    return notion.created[i][1]["Full text"]["rich_text"][0]["text"]["content"]


def _inbox_job(notion, i=0):
    rich = notion.created[i][1]["Job"]["rich_text"]
    return rich[0]["text"]["content"] if rich else ""


def test_text_starts_editor_for_the_one_waiting_job():
    notion = FakeNotion(ready=[_ready()])
    label, tg, _ = run(msg("Let's start with the CV"), notion)
    assert label == "editor-started" and notion.editor_started == [JID]
    assert _inbox_text(notion) == "Let's start with the CV" and _inbox_job(notion) == PAGE_ID
    assert notion.windows and notion.windows[0]["start"] > handle.now_iso()
    assert "minute and a half" in tg.sent[-1][0]


def test_second_text_during_boot_starts_nothing():
    notion = FakeNotion(live=_ready())
    label, _, _ = run(msg("and make it short"), notion)
    assert label == "inbox" and notion.editor_started == []
    assert _inbox_text(notion) == "and make it short"


def test_message_is_saved_before_the_run_starts():
    notion = FakeNotion(ready=[_ready()])
    saved_when_started = []
    run(msg("go"), notion, editor=lambda job: saved_when_started.append(len(notion.created)))
    assert saved_when_started == [1]


def test_drafting_job_can_be_resumed_by_text():
    notion = FakeNotion(ready=[_ready(status="Drafting")])
    assert run(msg("carry on"), notion)[0] == "editor-started"


def test_expired_window_starts_a_new_run():
    notion = FakeNotion(live=None, ready=[_ready(status="Drafting")])
    assert run(msg("are you there"), notion)[0] == "editor-started" and notion.editor_started == [JID]


def test_reply_to_a_brief_picks_that_job():
    notion = FakeNotion(page=_ready(), brief_for=900, ready=[_ready(), _ready(title="Other", pid=OTHER_ID)])
    label, _, _ = run(msg("start with the letter", reply_to=900), notion)
    assert label == "editor-started" and notion.editor_started == [JID]


def test_several_waiting_gives_buttons_and_keeps_text():
    notion = FakeNotion(ready=[_ready(title="One"), _ready(title="Two", pid=OTHER_ID)])
    label, tg, _ = run(msg("start the cv"), notion)
    assert label == "editor-choose" and notion.editor_started == []
    assert _inbox_job(notion) == "" and _inbox_text(notion) == "start the cv"
    assert tg.sent[-1][1][0] == [("One", f"pick:{JID}")]


def test_pick_files_the_waiting_message_and_starts():
    orphan = {"id": "orphan-1"}
    notion = FakeNotion(page=_ready(), orphans=[orphan])
    label, _, _ = run(tap(f"pick:{JID}"), notion)
    assert label == "editor-started" and notion.editor_started == [JID]
    assert notion.updates[0]["Job"]["rich_text"][0]["text"]["content"] == PAGE_ID


def test_no_job_waiting_gives_help():
    label, tg, _ = run(msg("hello?"), FakeNotion())
    assert label == "help" and tg.sent


def test_failed_dispatch_clears_window_keeps_message_and_says_why():
    notion = FakeNotion(ready=[_ready()])
    label, tg, _ = run(msg("go"), notion, editor=lambda job: "GitHub said 403: nope")
    assert label == "editor-failed" and notion.windows[-1] is None
    assert len(notion.created) == 1 and "403" in tg.sent[-1][0]


def test_greeting_still_works_with_a_job_waiting():
    assert run(msg("/help"), FakeNotion(ready=[_ready()]))[0] == "greeting"


def test_jobs_command_still_answered_mid_session():
    notion = FakeNotion(live=_ready())
    assert run(msg("jobs 55"), notion)[0] == "jobs-none" and notion.created == []


def test_start_button_saves_request_and_starts():
    notion = FakeNotion(page=_ready())
    label, _, _ = run(tap(f"start:{JID}:cv"), notion)
    assert label == "editor-started" and _inbox_text(notion) == "Start with the CV."


def test_start_button_during_that_jobs_chat_goes_to_the_chat():
    notion = FakeNotion(page=_ready(), live=_ready())
    label, _, _ = run(tap(f"start:{JID}:cv"), notion)
    assert label == "inbox" and notion.editor_started == []


def test_start_button_during_another_chat_says_so():
    notion = FakeNotion(page=_ready(), live=_ready(pid=OTHER_ID))
    label, tg, _ = run(tap(f"start:{JID}:cv"), notion)
    assert label == "busy" and notion.editor_started == [] and "another" in tg.sent[-1][0]


def test_skip_button_needs_no_session():
    notion = FakeNotion(page=_ready())
    label, tg, _ = run(tap(f"skipasset:{JID}:cv"), notion)
    assert label == "asset-skipped" and notion.editor_started == []
    assert notion.updates[-1] == {"State": {"select": {"name": "skipped"}}}
    assert "CV" in tg.sent[-1][0]


def test_restore_returns_a_dropped_job_to_briefed():
    notion = FakeNotion(page=_ready(status="Skipped"))
    label, _, _ = run(tap(f"restore:{JID}"), notion)
    assert label == "restored" and notion.page["properties"]["Status"]["select"]["name"] == "Briefed"


def test_restore_only_touches_a_skipped_job():
    assert run(tap(f"restore:{JID}"), FakeNotion(page=_ready(status="Applied")))[0] == "already"
