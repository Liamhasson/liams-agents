"""Pure unit tests for the Researcher helpers (no network/LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.researcher.run import _visible_text, _notes_text


def test_visible_text_strips_scripts_and_tags():
    html = "<html><head><style>.x{color:red}</style></head><body><h1>Acme</h1>" \
           "<script>evil()</script><p>We build&nbsp;tools.</p></body></html>"
    out = _visible_text(html)
    assert "Acme" in out and "We build" in out
    assert "evil" not in out and "color:red" not in out and "<" not in out


def test_notes_text_includes_sections_and_skips_empty_news():
    r = {"what_they_do": "A fintech.", "problem_behind_hire": "Scaling design.",
         "values_and_language": "Direct, fast.", "recent_news": "",
         "how_liam_fits": "Ships fast."}
    txt = _notes_text(r)
    assert "What they do" in txt and "A fintech." in txt
    assert "How you fit" in txt
    assert "Recent news" not in txt   # empty news omitted


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} researcher tests passed.")
