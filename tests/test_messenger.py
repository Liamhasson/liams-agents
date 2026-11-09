"""Pure unit tests for Messenger composition + callback parsing (no network)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.messenger.compose import job_card, ask_card, job_id_for_callback
from agents.messenger.handle import uuid as _uuid
from agents.messenger.send import send_order


def _page(**over):
    props = {
        "Title": {"type": "title", "title": [{"plain_text": "Product Designer"}]},
        "Company": {"type": "rich_text", "rich_text": [{"plain_text": "Acme"}]},
        "Location": {"type": "rich_text", "rich_text": [{"plain_text": "Berlin"}]},
        "Remote": {"type": "select", "select": {"name": "hybrid"}},
        "Score": {"type": "number", "number": 72},
        "Source": {"type": "rich_text", "rich_text": [{"plain_text": "Greenhouse:acme"}]},
        "Priority": {"type": "select", "select": {"name": "fresh"}},
        "Ghost risk": {"type": "select", "select": {"name": over.pop("ghost", "low")}},
        "Fit summary": {"type": "rich_text", "rich_text": [{"plain_text": "Own onboarding"}]},
        "Why Liam": {"type": "rich_text", "rich_text": [{"plain_text": "You ship fast"}]},
        "Gaps": {"type": "rich_text", "rich_text": [{"plain_text": ""}]},
        "URL": {"type": "url", "url": "https://acme.com/jobs/1"},
        "Field": {"type": "select", "select": {"name": over.pop("field", "other")}},
        "Remote eligibility": {"type": "select", "select": {"name": over.pop("elig", "berlin")}},
    }
    props["Score"]["number"] = over.pop("score", 72)
    props["Fit score"] = {"type": "number", "number": over.pop("fit", 60)}
    props["Application asks"] = {"type": "rich_text", "rich_text": [{"plain_text": over.pop("asks_json", "")}]}
    props["Ad work"] = {"type": "rich_text", "rich_text": [{"plain_text": over.pop("ad", "")}]}
    props["Flags"] = {"type": "multi_select", "multi_select": [{"name": f} for f in over.pop("flags", [])]}
    posted = over.pop("posted", "")
    props["Posted at"] = {"type": "date", "date": {"start": posted} if posted else None}
    return {"id": "407be63a-05ad-8160-bb8f-ed832bc3d9c2", "properties": props}


def test_job_card_has_apply_skip_buttons_with_job_id():
    page = _page()
    jid = job_id_for_callback(page)
    assert "-" not in jid and len(jid) == 32
    text, buttons = job_card(page)
    flat = [b for row in buttons for b in row]
    labels = {label for label, data in flat}
    datas = {data for label, data in flat}
    assert "✅ Brief me" in labels and "⏭ Skip" in labels
    assert f"apply:{jid}" in datas and f"skip:{jid}" in datas
    assert "Product Designer" in text and "Acme" in text
    assert "acme.com/jobs/1" in text          # url renders (was a bug: read as rich_text)


def test_job_card_shows_ghost_warning():
    _, _ = job_card(_page())
    text, _ = job_card(_page(ghost="high"))
    assert "ghost" in text.lower()


def test_ask_card_yes_no():
    text, buttons = ask_card(_page())
    datas = {d for row in buttons for (l, d) in row}
    jid = job_id_for_callback(_page())
    assert f"yes:{jid}" in datas and f"no:{jid}" in datas


def test_music_jobs_are_sent_first_then_berlin():
    remote_music = _page(field="music", elig="remote_de_ok", score=61)
    berlin_top = _page(score=95)
    remote_top = _page(elig="remote_de_ok", score=99)
    order = sorted([remote_top, berlin_top, remote_music], key=send_order)
    assert order == [remote_music, berlin_top, remote_top]


def test_job_card_shows_the_field():
    text, _ = job_card(_page(field="rock/live music"))
    assert "🎸 rock/live music" in text
    text, _ = job_card(_page(field="sport"))
    assert "· sport" in text
    assert "other" not in job_card(_page())[0]


def test_cards_show_the_score_breakdown():
    page = _page()
    page["properties"]["Score breakdown"] = {"type": "rich_text", "rich_text": [
        {"plain_text": "fit 52 · Berlin +10 · new post +15"}]}
    assert "<i>fit 52 · Berlin +10 · new post +15</i>" in job_card(page)[0]
    assert "fit 52" in ask_card(page)[0]


def _asks(*items):
    return json.dumps([{"kind": k, "state": st, "quote": "the post's words"} for k, st in items])


def test_card_shows_fit_not_out_of_100():
    text, _ = job_card(_page(score=118, fit=72))
    assert "Fit 72" in text and "/100" not in text


def test_card_lists_asks():
    assert "Loom (required)" in job_card(_page(asks_json=_asks(("loom_or_video", "required"))))[0]


def test_card_marks_what_is_not_wanted():
    assert "CV (not wanted)" in job_card(_page(asks_json=_asks(("cv", "not_wanted"))))[0]


def test_card_without_asks_says_so():
    assert "doesn't say what to send" in job_card(_page(asks_json="[]"))[0]


def test_card_says_nothing_for_jobs_scored_before_asks_existed():
    assert "what to send" not in job_card(_page(asks_json=""))[0]


def test_card_warns_ad_work():
    text = job_card(_page(ad="design ad campaigns"))[0]
    assert "Includes ad work" in text and "design ad campaigns" in text


def test_no_ad_warning_without_ad_work():
    assert "ad work" not in job_card(_page())[0]


def test_card_shows_senior_label():
    assert "Senior title" in job_card(_page(flags=["senior"]))[0]
    assert "Senior title" not in job_card(_page())[0]


def test_card_button_says_brief_me():
    assert job_card(_page())[1][0][0][0] == "✅ Brief me"


def test_card_says_posted_days_ago():
    posted = (datetime.now(timezone.utc) - timedelta(days=12)).date().isoformat()
    assert "posted 12 days ago" in job_card(_page(posted=posted))[0]


def test_card_without_a_date_says_nothing_about_age():
    assert "posted" not in job_card(_page())[0]


def test_borderline_card_shows_fit():
    text, buttons = ask_card(_page(score=47, fit=52))
    assert "Fit 52" in text and "/100" not in text


def test_uuid_roundtrip():
    assert _uuid("407be63a05ad8160bb8fed832bc3d9c2") == "407be63a-05ad-8160-bb8f-ed832bc3d9c2"
    assert _uuid("407be63a-05ad-8160-bb8f-ed832bc3d9c2") == "407be63a-05ad-8160-bb8f-ed832bc3d9c2"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} messenger tests passed.")
