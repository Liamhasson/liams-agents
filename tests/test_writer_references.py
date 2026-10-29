"""Tests for drafting from Liam's approved references (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.writer import converse, references
from agents.writer.context import NeverAgain, Reference, WriterContext, parse_reference

STORY = ("I spent years booking shows, so I know how a release night can go wrong in more "
         "ways than one, and I ran the budgets, the visuals and the bookings myself.")
LETTER = ("Hi Acme team,\n\nI applied for the Product Designer role because it fits my background.\n\n"
          f"{STORY}\n\nAt Beta nobody had asked for a redesign. I pitched one and they hired me.\n\n"
          "I'd be glad to show you the tool and talk properly.\n\nThanks, Sam")


def _ref(title, kind="cover letter", company="Acme", role="Product Designer",
         role_type="product design", approved="2026-10-28", text=LETTER):
    return Reference(title, kind, company, role, role_type, approved, text)


def _ctx(company="Zeta", title="Product Designer", role_type="product design", refs=(), never=()):
    return WriterContext("job", title, company, "Berlin", role_type, "", "", "", "", "guide", "cv",
                         list(never), list(refs))


def test_parse_reference_reads_meta_then_text():
    page = ("Type: cover letter\nCompany: Acme\nRole: Product Designer\nRole type: product design\n"
            "Approved: 2026-10-28\nHi Acme team,\nFirst paragraph.\nThanks, Sam")
    r = parse_reference("Acme cover letter", page)
    assert (r.kind, r.company, r.approved) == ("cover letter", "Acme", "2026-10-28")
    assert r.text == "Hi Acme team,\n\nFirst paragraph.\n\nThanks, Sam"
    cv = parse_reference("Acme resume", "Type: CV\nCompany: Acme\n# Sam\n## Summary\n- A line.")
    assert cv.kind == "CV" and cv.text == "# Sam\n## Summary\n- A line."


def test_story_paragraphs_drop_greeting_opening_closing_and_sign_off():
    paras = references.story_paragraphs(LETTER)
    assert paras == [STORY, "At Beta nobody had asked for a redesign. I pitched one and they hired me."]


def test_story_paragraphs_keep_a_link_with_its_paragraph():
    letter = LETTER.replace(STORY, STORY + "\n\nhttps://example.com/")
    assert references.story_paragraphs(letter)[0] == STORY + "\nhttps://example.com/"


def test_pick_prefers_same_company_then_role_then_newest():
    same = _ref("Zeta letter", company="Zeta", role="Brand Designer", role_type="brand or visual")
    close_old = _ref("Old close", approved="2026-01-01")
    close_new = _ref("New close", approved="2026-10-01")
    far = _ref("Far", role="Sound Engineer", role_type="audio")
    cv = _ref("Acme resume", kind="CV", text="# Sam")
    picked = references.pick(_ctx(refs=[far, close_old, cv, same, close_new]))
    assert [r.title for r in picked] == ["Zeta letter", "New close", "Acme resume"]


def test_block_shows_only_story_paragraphs_never_the_opening_or_closing():
    text = references.block([_ref("Acme cover letter")])
    assert STORY in text and "I applied for" not in text and "glad to show you" not in text


def test_reused_counts_sentences_copied_word_for_word():
    draft = f"Hi Zeta team,\n\nSomething new and specific for Zeta here.\n\n{STORY}\n\nThanks, Sam"
    assert references.reused(draft, [_ref("Acme cover letter")], "cover letter") == {"Acme cover letter": 1}


def test_approved_sentences_skip_style_lint_but_not_rejected_lines():
    ctx = _ctx(refs=[_ref("Acme cover letter")], never=[NeverAgain("I pitched one and they hired me.", "x")])
    draft = f"{STORY} I pitched one and they hired me."
    issues = converse.voice_issues(ctx, draft, "cover letter")
    assert "3+ commas in a sentence" not in issues  # his approved sentence has 3 commas
    assert "rejected line: I pitched one and they hired me." in issues
    assert "3+ commas in a sentence" in converse.voice_issues(_ctx(), STORY, "cover letter")


def test_references_only_go_into_the_final_draft_prompt():
    ctx = _ctx(refs=[_ref("Acme cover letter")])
    assert "APPROVED REFERENCES" in converse.build_system(ctx, with_references=True)
    assert "APPROVED REFERENCES" not in converse.build_system(ctx)
    assert "APPROVED REFERENCES" not in converse.build_system(_ctx(), with_references=True)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} writer reference tests passed.")
