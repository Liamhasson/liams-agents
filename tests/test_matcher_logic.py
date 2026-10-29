"""Pure unit tests for the Matcher's routing + hard-drop logic (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.matcher.score import (route, is_hard_drop, assess_ghost, freshness, with_bonus,
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


FIELDS = {"rock/live music": 20, "music": 15, "sport": 8, "cyber": 8}


def _f(score, field, remote="remote_de_ok"):
    return {**_r(score, remote=remote), "field": field}


def test_berlin_roles_get_the_bonus_and_others_dont():
    assert with_bonus(_f(55, "other", remote="berlin"), 10, FIELDS) == 65
    assert with_bonus(_f(95, "other", remote="berlin"), 10, FIELDS) == 100
    assert with_bonus(_f(55, "other"), 10, FIELDS) == 55


def test_favourite_fields_score_higher_and_others_are_untouched():
    assert with_bonus(_f(50, "rock/live music"), 10, FIELDS) == 70
    assert with_bonus(_f(50, "music"), 10, FIELDS) == 65
    assert with_bonus(_f(50, "cyber"), 10, FIELDS) == 58
    assert with_bonus(_f(50, "other"), 10, FIELDS) == 50
    assert with_bonus({**_r(50)}, 10, FIELDS) == 50          # no field given
    assert with_bonus(_f(50, "music", remote="berlin"), 10, FIELDS) == 75   # bonuses add up


def test_a_music_bonus_never_overrules_the_hard_rules():
    res = _f(90, "music")
    res["score"] = with_bonus(res, 10, FIELDS)
    assert route({**res, "german_required": "fluent"}, ALERT, ASK)[0] == "dropped"
    assert route({**res, "remote_eligibility": "no"}, ALERT, ASK)[0] == "dropped"


def test_onsite_outside_berlin():
    assert onsite_outside_berlin("London", "")
    assert onsite_outside_berlin("Munich HQ", "")
    assert onsite_outside_berlin("Bristol; London", "")
    assert not onsite_outside_berlin("Berlin, Germany", "")
    assert not onsite_outside_berlin("London or Berlin", "")
    assert not onsite_outside_berlin("London", "yes")        # remote job
    assert not onsite_outside_berlin("Remote - Europe", "")
    assert not onsite_outside_berlin("", "")                 # unknown: Claude decides


def test_written_in_german():
    de = ("Wir suchen dich als Designer:in für unser Team in Berlin. Du arbeitest mit uns an "
          "der App und bist für die Gestaltung von Features verantwortlich. Was du mitbringst: "
          "Erfahrung im Design, eine klare Haltung und Lust auf Verantwortung. Wir bieten dir ein "
          "Team, das mit dir wächst, und die Möglichkeit, die Zukunft der Pflege mit uns zu gestalten. ") * 2
    en = ("We are looking for a Product Designer to join our team in Berlin. You will work with "
          "engineers and own the design of features. German is a plus, not a must. ") * 4
    en_with_german_footer = en + "Wir freuen uns auf deine Bewerbung und auf das Gespräch mit dir."
    assert written_in_german(de)
    assert not written_in_german(en)
    assert not written_in_german(en_with_german_footer)


def test_long_description_is_stored_in_pieces():
    pieces = _long_rt("x" * 4500)["rich_text"]
    assert [len(p["text"]["content"]) for p in pieces] == [2000, 2000, 500]
    assert len("".join(p["text"]["content"] for p in _long_rt("y" * 9000)["rich_text"])) == 6000


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
