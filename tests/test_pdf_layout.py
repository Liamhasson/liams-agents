"""Pure tests for the CV/cover letter HTML layout (no browser, no network)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.pdf.generator import _cover_letter_to_html, _markdown_cv_to_html, parse_header

CV = """# Jane Doe
Product Designer
jane@example.com · Berlin · example.com

## Experience
### Designer, Acme | Aug 2026 - Present
- Shipped a thing.

## Projects
### Pulse, UX Case Study | Dec 2025 - Feb 2026
_Designed a fitness app end to end._
- Ran two rounds of testing.

## Skills
**Tools:** Figma · Claude Code
"""


def test_header_parsed():
    assert parse_header(CV) == ("Jane Doe", "Product Designer", "jane@example.com · Berlin · example.com")


def test_entry_has_title_and_formatted_date():
    html = _markdown_cv_to_html(CV)
    assert '<span class="role-title">Designer, Acme</span>' in html
    assert '<span class="role-date">Aug 2026 – Present</span>' in html


def test_contact_links_and_italic_desc():
    html = _markdown_cv_to_html(CV)
    assert 'href="mailto:jane@example.com"' in html and 'href="https://example.com"' in html
    assert '<div class="role-desc">Designed a fitness app end to end.</div>' in html
    assert "<strong>Tools:</strong>" in html


def test_cover_letter_shares_cv_header():
    html = _cover_letter_to_html("Hi Acme team,\n\nA line.\n\nThanks, Jane", parse_header(CV))
    assert '<div class="cv-name">Jane Doe</div>' in html
    assert '<p class="signature">Thanks, Jane</p>' in html


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} pdf layout tests passed.")
