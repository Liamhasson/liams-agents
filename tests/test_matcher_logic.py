"""Pure unit tests for the Matcher's routing + hard-drop logic (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.matcher.score import route, is_hard_drop

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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} matcher logic tests passed.")
