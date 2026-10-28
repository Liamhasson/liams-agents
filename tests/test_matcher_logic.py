"""Pure unit tests for the Matcher's routing + hard-drop logic (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.matcher.score import route, is_hard_drop, assess_ghost, freshness

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
