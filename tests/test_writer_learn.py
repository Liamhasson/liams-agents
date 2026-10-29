"""Tests for the Writer learning from Liam's edits (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.writer import learn, session
from agents.writer.context import NeverAgain, WriterContext

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


def test_candidates_skip_lines_liam_only_added_words_to():
    changes = [learn.Change("Nobody had asked for a redesign.", "At Acme nobody had asked for a redesign.")]
    assert learn.candidates(changes, []) == []


def test_candidates_skip_added_lines_and_known_entries():
    changes = [learn.Change("Old slogan.", "New line."), learn.Change(None, "Brand new line."),
               learn.Change("Already banned.", None), learn.Change("Old slogan.", "Again.")]
    known = [NeverAgain("already banned.", "x")]
    assert learn.candidates(changes, known) == [learn.Change("Old slogan.", "New line.")]


def test_reason_quotes_liams_fix_and_never_guesses():
    assert learn.reason(learn.Change("a", "b")) == 'Liam rewrote it as: "b"'
    assert learn.reason(learn.Change("a", None)) == "Liam cut it."


def test_parse_pick():
    assert learn.parse_pick("all", 3) == [0, 1, 2]
    assert learn.parse_pick("None.", 3) == []
    assert learn.parse_pick("1, 3", 3) == [0, 2]
    assert learn.parse_pick("2 and 1", 3) == [0, 1]
    assert learn.parse_pick("4", 3) is None
    assert learn.parse_pick("change the closing", 3) is None


def test_confirm_message_escapes_html():
    msg = learn.confirm_message([("cover letter", learn.Change("Design & <Insights>", None))])
    assert "Design &amp; &lt;Insights&gt;" in msg and "Add it to" in msg


# ---- the session flow, with Telegram, Notion and Claude faked ----------------

class FakeTelegram:
    def __init__(self, replies):
        self.replies, self.sent, self.next_id = list(replies), [], 1

    def get_updates(self, offset=None, timeout=0):
        if not self.replies:
            return []
        upd = {"update_id": self.next_id, "message": {"chat": {"id": "42"}, "text": self.replies.pop(0)}}
        self.next_id += 1
        return [upd]

    def send_message(self, chat, text, buttons=None):
        self.sent.append(text)

    def send_document(self, chat, path, caption=""):
        self.sent.append(f"[doc] {caption}")


class FakeNotion:
    def __init__(self):
        self.updates = []

    def update_page(self, page_id, props):
        self.updates.append(props)

    def ensure_databases(self):
        return {"Jobs": "jobs"}


def _run_session(replies, revised_letter=FINAL):
    # The session drains one batch of old updates first, so lead with a stale message.
    tg, notion, saved, added = FakeTelegram(["(old message)"] + replies), FakeNotion(), [], []
    ctx = WriterContext("job1", "Designer", "Acme", "Berlin", "product design", "", "", "", "",
                        "", "", [NeverAgain("Already banned.", "x")])
    first = {"cv_markdown": "# Sam\n- Led the launch.", "cover_letter_markdown": FIRST, "review_log": []}
    fakes = {
        (session, "NotionClient"): lambda: notion,
        (session, "Telegram"): lambda: tg,
        (session, "Claude"): lambda model=None: type("C", (), {"cost_summary": lambda self: ""})(),
        (session, "_pick_job"): lambda n, db, j: {"id": "job1"},
        (session.ctxmod, "build_context"): lambda n, job: ctx,
        (session.converse, "opening"): lambda c, x: "Hi",
        (session.converse, "finalize"): lambda c, x, h: dict(first),
        (session.converse, "revise"): lambda c, x, d, r: {
            "cv_markdown": d["cv_markdown"], "cover_letter_markdown": revised_letter, "note": "Done."},
        (session, "_send_pack"): lambda *a: None,
        (session.learn, "save_reference"): lambda *a: saved.append(a[1]),
        (session.learn, "add_never_again"): lambda *a: added.append(a[1:]),
        (session.config, "require"): lambda key: "42",
    }
    originals = {k: getattr(*k) for k in fakes}
    try:
        for (mod, name), fake in fakes.items():
            setattr(mod, name, fake)
        result = session.run(minutes=0.05)
    finally:
        for (mod, name), orig in originals.items():
            setattr(mod, name, orig)
    return result, tg, notion, saved, added


def test_session_counts_edits_saves_references_and_adds_only_picked_lines():
    result, tg, notion, saved, added = _run_session(["done", "swap the invented line", "approve", "1"])
    assert result == {"drafted": 1, "approved": True}
    assert saved == ["Acme resume", "Acme cover letter"]
    assert {"Lines changed": {"number": 2}}.items() <= notion.updates[-2].items()
    assert notion.updates[-1] == {"Status": {"select": {"name": "Ready to send"}}}
    assert added == [("So I invented a system from scratch.",
                      'Liam rewrote it as: "So I built a way to check."', "cover letter", "Acme, Designer")]
    assert any("You changed 2 lines" in m for m in tg.sent)


def test_session_approve_without_edits_asks_nothing():
    result, tg, notion, saved, added = _run_session(["done", "approve"])
    assert result["approved"] and added == []
    assert {"Lines changed": {"number": 0}}.items() <= notion.updates[-2].items()
    assert not any("Never again list?" in m for m in tg.sent)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} writer learning tests passed.")
