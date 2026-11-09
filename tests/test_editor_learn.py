"""Tests for the Writer learning from Liam's edits (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.editor import learn

FIRST = ("Hi team,\n\nI built a tool for bookers. So I invented a system from scratch. "
         "It checks every show.\n\nThe second story is the same shape. I pitched a redesign.\n\n"
         "Thanks, Sam")
FINAL = ("Hi team,\n\nI built a tool for bookers. So I built a way to check. "
         "It checks every show.\n\nI pitched a redesign.\n\nThanks, Sam")


def test_diff_finds_replaced_and_cut_sentences():
    changes = learn.diff(FIRST, FINAL, "cover letter")
    assert learn.Change("So I invented a system from scratch.", "So I built a way to check.") in changes
    assert learn.Change("The second story is the same shape.", None) in changes
    assert len(changes) == 2


def test_diff_of_identical_text_is_empty():
    assert learn.diff(FIRST, FIRST, "cover letter") == []


def test_cv_diff_is_line_by_line_and_ignores_bullet_markers():
    before = "## Experience\n- Led the launch.\n- Shipped it fast."
    after = "## Experience\n* Led the launch.\n- Shipped it in three weeks."
    assert learn.diff(before, after, "CV") == [learn.Change("Shipped it fast.", "Shipped it in three weeks.")]


def test_diff_pairs_a_merged_sentence_with_the_line_it_became():
    before = "Intro line here. The second story is the same shape. Nobody had asked for a redesign. End."
    after = "Intro line here. At Acme nobody had asked for a redesign. End."
    assert learn.diff(before, after, "cover letter") == [
        learn.Change("The second story is the same shape.", None),
        learn.Change("Nobody had asked for a redesign.", "At Acme nobody had asked for a redesign."),
    ]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Editor line-count tests passed.")
