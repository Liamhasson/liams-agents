"""Pure unit tests for Messenger composition + callback parsing (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.messenger.compose import job_card, ask_card, job_id_for_callback
from agents.messenger.poll import _uuid
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
    return {"id": "407be63a-05ad-8160-bb8f-ed832bc3d9c2", "properties": props}


def test_job_card_has_apply_skip_buttons_with_job_id():
    page = _page()
    jid = job_id_for_callback(page)
    assert "-" not in jid and len(jid) == 32
    text, buttons = job_card(page)
    flat = [b for row in buttons for b in row]
    labels = {label for label, data in flat}
    datas = {data for label, data in flat}
    assert "✅ Apply" in labels and "⏭ Skip" in labels
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


def test_uuid_roundtrip():
    assert _uuid("407be63a05ad8160bb8fed832bc3d9c2") == "407be63a-05ad-8160-bb8f-ed832bc3d9c2"
    assert _uuid("407be63a-05ad-8160-bb8f-ed832bc3d9c2") == "407be63a-05ad-8160-bb8f-ed832bc3d9c2"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} messenger tests passed.")
