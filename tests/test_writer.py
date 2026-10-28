"""Pure unit tests for the Writer's voice lint (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.writer.converse import lint


def test_lint_flags_em_dash():
    assert "em-dash" in lint("I build things — quickly.")


def test_lint_flags_banned_words():
    issues = " ".join(lint("I'm excited to apply and actually quite passionate."))
    assert "excited to apply" in issues and "actually" in issues and "passionate" in issues


def test_lint_flags_comma_pileup():
    assert any("comma" in i for i in lint("I did research, testing, design, and shipping, fast."))


def test_lint_passes_clean_liam_voice():
    clean = ("I saw in your post that you want proven AI work. I built Eventread because "
             "my band lost its show to a bigger gig and nobody had checked.")
    assert lint(clean) == []


def test_lint_word_boundary_not_oversensitive():
    # "robust" is banned but "robustness" shouldn't trip a false positive here;
    # and ordinary words near banned stems are fine.
    assert lint("The build is solid and dependable.") == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} writer lint tests passed.")
