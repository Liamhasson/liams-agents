"""Pure unit tests for the Writer's voice lint (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.editor.context import NeverAgain
from agents.editor.context import EditorContext
from agents.editor.converse import _rejected_block, build_system, fact_check, lint, review

NEVER = [
    NeverAgain("I've been a Replika user.", "Invented.", "shared"),
    NeverAgain("I'd love to hear what the blank page looks like right now.", "Vague.", "cover letter"),
    NeverAgain("Passion for pixel-perfect craft.", "Slogan.", "CV"),
]


def test_lint_flags_every_dash():
    for s in ("I build things — quickly.", "I build things – quickly.", "I build things - quickly."):
        assert "dash in a sentence" in lint(s), s


def test_lint_flags_salary_in_letter():
    assert any("salary" in i for i in lint("My salary range is €X to €Y gross per year."))


def test_lint_flags_parentheses_in_letter_not_cv():
    assert "parentheses in a letter" in lint("I built it (solo) in four months.")
    assert lint("**Languages:** English (Fluent) · German (A2)", "CV") == []


def test_lint_allows_cv_date_ranges():
    cv = "### Founder & Product Designer, Eventread | Mar 2026 - Present\n- Shipped a SaaS in under 4 months."
    assert lint(cv, "CV") == []


def test_lint_thousands_separator_is_not_a_comma():
    assert lint("I checked the bands, which sit on Safe, Threat or Critical, against 3,172 listings.") != []
    assert lint("I checked Safe, Threat or Critical bands against 3,172 real listings.") == []


def test_lint_cv_headings_dont_count_toward_commas():
    cv = ("### Founder & Creative Director, 2 Music Projects | 2016 - 2024\n"
          "- Founded two projects and led brand, design, video and release marketing over 8 years.")
    assert lint(cv, "CV") == []


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


def test_lint_blocks_never_again_lines_despite_case_quotes_and_spacing():
    issues = lint("Hi team. I’ve been a  REPLIKA user and I build things.", never_again=NEVER)
    assert "rejected line: I've been a Replika user." in issues


def test_lint_never_again_respects_applies_to():
    blank = "I'd love to hear what the blank page looks like right now."
    assert any("rejected line" in i for i in lint(blank, never_again=NEVER))
    assert not any("rejected line" in i for i in lint(blank, "CV", never_again=NEVER))
    craft = "- Passion for pixel-perfect craft."
    assert any("rejected line" in i for i in lint(craft, "CV", never_again=NEVER))
    assert not any("rejected line" in i for i in lint(craft, never_again=NEVER))


def test_lint_without_never_again_list_is_unchanged():
    assert lint("I've been a Replika user.") == []


def test_rejected_block_filters_by_kind():
    block = _rejected_block(NEVER, "CV")
    assert "Replika user" in block and "pixel-perfect" in block and "blank page" not in block
    assert _rejected_block([], "CV") == "(none yet)"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} writer lint tests passed.")


def _ctx(description="", brief=""):
    return EditorContext("job1", "Designer", "Acme", "Berlin", "product design", description, "", "", "",
                         "voice guide", "cv text", brief=brief)


def test_system_prompt_has_full_post_and_brief():
    post = "word " * 1000 + "LASTWORD"
    system = build_system(_ctx(description=post, brief="They want a builder."))
    assert "LASTWORD" in system and "They want a builder." in system


def test_brief_is_labelled_as_not_a_source_of_facts():
    assert "not a source of facts" in build_system(_ctx(brief="x"))


def test_prompt_no_longer_assumes_a_cover_letter():
    assert "cover letter for this role or just the CV" not in build_system(_ctx())


def test_weak_spots_never_reach_the_editor():
    brief = "<b>Why you</b>\n• Strong\n\n<b>Weak spots</b>\n• No mobile work\n\n<b>What to send</b>\n• CV"
    system = build_system(_ctx(brief=brief))
    assert "No mobile work" not in system and "Strong" in system and "What to send" in system


def test_fact_check_and_review_see_the_whole_post():
    calls = []

    class Model:
        def json_call(self, system, user, schema, **k):
            calls.append(system)
            return {"problems": [], "corrected": "x", "claims": []}

    post = "word " * 1000 + "LASTWORD"
    ctx = _ctx(description=post)
    fact_check(Model(), ctx, "d", "CV")
    review(Model(), ctx, "d", "CV", [])
    assert all("LASTWORD" in s for s in calls)


def test_a_rejected_old_line_is_not_a_source_for_the_fact_check():
    calls = []

    class Model:
        def json_call(self, system, user, schema, **k):
            calls.append(system)
            return {"claims": [], "corrected": "x"}

    ctx = _ctx()
    ctx.mytone = 'guide\n[Acme, CV, 2026-11-09] Instead of "I used their app", Liam wrote "I read about it".\n[Acme, CV, 2026-11-09] Liam said: "I freelance".'
    fact_check(Model(), ctx, "d", "CV")
    assert "I used their app" not in calls[0] and "I freelance" in calls[0]
