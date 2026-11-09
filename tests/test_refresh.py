"""The daily freshness refresh: post age changes the order, never re-sends a card (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.matcher import refresh
from agents.matcher.refresh import refreshed, with_age

RULES = {"bonus_min_fit": 40, "age_points": {1: 20, 3: 15, 7: 10, 15: 0, 30: -10, 45: -15}, "age_points_after": -20}
NOW_NEW = "2026-10-02T00:00:00+00:00"
NOW_OLD = "2026-11-20T00:00:00+00:00"


def test_refresh_drops_freshness_over_time():
    assert refreshed(80, 70, "2026-10-01", NOW_NEW, RULES) == (100, "new post +20")
    assert refreshed(80, 70, "2026-10-01", NOW_OLD, RULES) == (60, "old post -20")


def test_refresh_gives_no_bonus_below_bonus_min_fit():
    assert refreshed(30, 30, "2026-10-01", NOW_NEW, RULES) == (30, "")


def test_refresh_applies_old_penalty_at_any_fit():
    assert refreshed(30, 30, "2026-10-01", NOW_OLD, RULES) == (10, "old post -20")


def test_refresh_never_goes_below_zero():
    assert refreshed(5, 30, "2026-10-01", NOW_OLD, RULES)[0] == 0


def test_unknown_date_changes_nothing():
    assert refreshed(80, 70, "", NOW_NEW, RULES) == (80, "")


def test_age_part_is_replaced_in_place():
    assert with_age("fit 72 · Berlin +10 · new post +20 · asks 5 yrs -20", "old post -10") == \
        "fit 72 · Berlin +10 · old post -10 · asks 5 yrs -20"


def test_age_part_is_added_when_missing():
    assert with_age("fit 72 · Berlin +10", "new post +10") == "fit 72 · Berlin +10 · new post +10"


def test_age_part_is_removed_when_zero():
    assert with_age("fit 72 · new post +10", "") == "fit 72"


class FakeTelegramMustNotBeUsed:
    def __getattr__(self, name):
        raise AssertionError("refresh must never message Liam")


class FakeNotion:
    def __init__(self, pages):
        self.pages, self.updates = pages, []

    def query_database(self, db, filter=None):
        return self.pages

    def update_page(self, page_id, props):
        self.updates.append((page_id, props))


def _page(base, fit=70, posted="2026-10-01", score=100):
    return {"id": "p1", "properties": {
        "Base score": {"type": "number", "number": base},
        "Fit score": {"type": "number", "number": fit},
        "Score": {"type": "number", "number": score},
        "Posted at": {"type": "date", "date": {"start": posted}},
        "Priority": {"type": "select", "select": {"name": "fresh"}},
        "Score breakdown": {"type": "rich_text", "rich_text": [{"plain_text": "fit 70 · new post +20"}]},
    }}


def test_run_updates_score_priority_and_breakdown():
    n = FakeNotion([_page(80)])
    out = refresh.apply(n, "jobs", ["Waiting for Liam"], RULES, NOW_OLD)
    assert out == {"refreshed": 1}
    props = n.updates[0][1]
    assert props["Score"] == {"number": 60} and props["Priority"] == {"select": {"name": "older"}}
    assert props["Score breakdown"]["rich_text"][0]["text"]["content"] == "fit 70 · old post -20"


def test_run_skips_jobs_scored_before_base_score_existed():
    n = FakeNotion([_page(None)])
    assert refresh.apply(n, "jobs", ["Waiting for Liam"], RULES, NOW_OLD) == {"refreshed": 0} and n.updates == []


def test_run_writes_nothing_when_nothing_changed():
    page = _page(80, score=100)
    page["properties"]["Priority"]["select"]["name"] = "fresh"
    n = FakeNotion([page])
    assert refresh.apply(n, "jobs", ["Waiting for Liam"], RULES, "2026-10-01T12:00:00+00:00") == {"refreshed": 0}
