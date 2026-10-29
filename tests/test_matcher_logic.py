"""Pure unit tests for the Matcher's routing + hard-drop logic (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.matcher.score import (route, is_hard_drop, assess_ghost, freshness, adjust, age_points,
                                  onsite_outside_berlin, written_in_german)
from shared.notion.client import _long_rt

ALERT, ASK = 70, 40


def _r(score, german="none", remote="remote_de_ok"):
    return {"score": score, "german_required": german, "remote_eligibility": remote}


def test_high_score_alerts():
    assert route(_r(85), ALERT, ASK) == ("alert", "")


def test_mid_score_asks():
    decision, _ = route(_r(55), ALERT, ASK)
    assert decision == "ask"


def test_low_score_dropped():
    decision, reason = route(_r(20), ALERT, ASK)
    assert decision == "dropped" and "low score" in reason


def test_fluent_german_dropped_even_if_high_score():
    decision, reason = route(_r(90, german="fluent"), ALERT, ASK)
    assert decision == "dropped" and "German" in reason


def test_not_hirable_in_germany_dropped():
    decision, reason = route(_r(80, remote="no"), ALERT, ASK)
    assert decision == "dropped" and "Germany" in reason


def test_basic_german_is_fine():
    assert route(_r(75, german="basic"), ALERT, ASK)[0] == "alert"


def test_unclear_location_is_never_an_alert():
    assert route(_r(90, remote="unclear"), ALERT, ASK) == ("ask", "")


RULES = {
    "bonus_min_fit": 40, "berlin_bonus": 10, "role_bonus": {"product design": 10},
    "field_bonus": {"rock/live music": 20, "music": 15, "sport": 8, "cyber": 8},
    "liam_years": {"product": 2, "brand": 3, "graphic/visual": 5},
    "experience_penalty": {2: 10, 3: 20}, "experience_max_gap": 3,
}


def _j(fit, field="other", remote="remote_de_ok", role="UX/UI", years=0, discipline="product"):
    return {**_r(fit, remote=remote), "field": field, "role_type": role,
            "years_required": years, "discipline": discipline}


def score_of(job, age=0):
    return adjust(job, RULES, age)[0]


def test_berlin_roles_get_the_bonus_and_others_dont():
    assert score_of(_j(55, remote="berlin")) == 65
    assert score_of(_j(95, remote="berlin")) == 100
    assert score_of(_j(55)) == 55


def test_favourite_fields_score_higher_and_others_are_untouched():
    assert score_of(_j(50, "rock/live music")) == 70
    assert score_of(_j(50, "music")) == 65
    assert score_of(_j(50, "cyber")) == 58
    assert score_of(_j(50)) == 50
    assert score_of({**_r(50)}) == 50                       # nothing extra given
    assert score_of(_j(50, "music", remote="berlin")) == 75  # bonuses add up


def test_product_design_roles_score_higher():
    assert score_of(_j(50, role="product design")) == 60
    assert score_of(_j(50, role="brand or visual", discipline="brand")) == 50
    assert score_of(_j(50, role="product design", discipline="brand")) == 50   # mislabelled brand job


def test_bonuses_only_go_to_jobs_that_already_fit():
    festival_sales = _j(15, "rock/live music", remote="berlin", role="other")
    assert score_of(festival_sales, age=20) == 15
    assert score_of(_j(40, "rock/live music", remote="berlin"), age=20) == 90


def test_penalties_apply_whatever_the_fit():
    assert score_of(_j(30), age=-20) == 10
    assert score_of(_j(30, years=5)) == 10


def test_years_are_compared_with_liams_years_in_that_discipline():
    assert score_of(_j(70, years=3)) == 70                              # product, 1 beyond
    assert score_of(_j(70, years=4)) == 60                              # product, 2 beyond
    assert score_of(_j(70, years=5)) == 50                              # product, 3 beyond
    assert score_of(_j(70, years=5, discipline="brand")) == 60          # brand: 3 years
    assert score_of(_j(70, years=6, discipline="graphic/visual")) == 70  # graphic: 5 years
    assert score_of(_j(15, years=5)) == 0                               # never below 0


def test_too_many_years_is_dropped_even_for_music():
    decision, reason = route(_j(95, "music", years=6), ALERT, ASK, RULES)
    assert decision == "dropped" and "6+ years" in reason
    assert route(_j(95, years=5), ALERT, ASK, RULES)[0] == "alert"
    assert route(_j(95, years=6, discipline="brand"), ALERT, ASK, RULES)[0] == "alert"


AGE = {1: 20, 3: 15, 7: 10, 15: 0, 30: -10, 45: -15}


def test_newer_posts_score_higher_and_old_ones_lower():
    now = "2026-10-29T12:00:00+00:00"
    pts = lambda posted: age_points(posted, now, AGE, -20)
    assert pts("2026-10-29T02:00:00+00:00") == 20     # 10 hours
    assert pts("2026-10-27T12:00:00+00:00") == 15     # 2 days
    assert pts("2026-10-24") == 10                    # 5 days
    assert pts("2026-10-19") == 0                     # 10 days
    assert pts("2026-10-09") == -10                   # 20 days
    assert pts("2026-09-24") == -15                   # 35 days
    assert pts("2026-08-01") == -20                   # 89 days
    assert pts("") == 0                               # unknown date
    assert score_of(_j(70), age=20) == 90


def test_breakdown_shows_how_the_score_was_made():
    total, parts = adjust(_j(52, "music", remote="berlin", role="product design", years=4), RULES, 15)
    assert parts == ["fit 52", "Berlin +10", "product design +10", "music +15",
                     "new post +15", "asks 4 yrs -10"]
    assert total == 92


def test_a_music_bonus_never_overrules_the_hard_rules():
    res = _j(90, "music")
    res["score"] = score_of(res)
    assert route({**res, "german_required": "fluent"}, ALERT, ASK, RULES)[0] == "dropped"
    assert route({**res, "remote_eligibility": "no"}, ALERT, ASK, RULES)[0] == "dropped"


def test_hard_drop_working_student():
    kws = ["working student", "werkstudent"]
    assert is_hard_drop("Werkstudent Product Design (m/w/d)", "", kws)
    assert is_hard_drop("Product Designer", "This is a working student role", kws)
    assert not is_hard_drop("Product Designer", "Full-time permanent role", kws)


def test_ghost_content_high_respected():
    risk, _ = assess_ghost("high", "2026-10-20", "2026-10-20", "2026-10-28")
    assert risk == "high"


def test_ghost_fresh_specific_stays_low():
    risk, reasons = assess_ghost("low", "2026-10-25", "2026-10-25", "2026-10-28")
    assert risk == "low" and reasons == []


def test_ghost_age_bumps_risk():
    # first seen ~210 days ago, content said low -> age pushes to high
    risk, reasons = assess_ghost("low", "2026-04-01", "2026-04-01", "2026-10-28")
    assert risk == "high" and any(("seen for" in r or "posted" in r) for r in reasons)


def test_ghost_moderate_age_is_medium_not_high():
    # ~100 days -> medium under the softened thresholds, not high
    risk, _ = assess_ghost("low", "2026-07-20", "2026-07-20", "2026-10-28")
    assert risk == "medium"


def test_freshness_tiers():
    assert freshness("2026-10-28T08:00:00+00:00", "2026-10-28T20:00:00+00:00") == "fresh"   # 12h
    assert freshness("2026-10-25", "2026-10-28") == "recent"                                # 3d
    assert freshness("2026-09-01", "2026-10-28") == "older"                                 # ~8w
    assert freshness("", "2026-10-28") == "recent"                                          # unknown


def test_ghost_repost_detected():
    # posting date is 20 days after we first saw it -> reposted
    risk, reasons = assess_ghost("low", "2026-10-01", "2026-10-25", "2026-10-28")
    assert risk == "high" and any("reposted" in r for r in reasons)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} matcher logic tests passed.")
