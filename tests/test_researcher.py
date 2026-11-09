"""Pure unit tests for the Researcher helpers (no network/LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.researcher.run import RESEARCH_SCHEMA, _notes_text, _visible_text, read_site, website_url


def test_visible_text_strips_scripts_and_tags():
    html = "<html><head><style>.x{color:red}</style></head><body><h1>Acme</h1>" \
           "<script>evil()</script><p>We build&nbsp;tools.</p></body></html>"
    out = _visible_text(html)
    assert "Acme" in out and "We build" in out
    assert "evil" not in out and "color:red" not in out and "<" not in out


def _res(**over):
    return {"what_they_do": "A fintech.", "problem_behind_hire": "Scaling design.",
            "values_and_language": "Direct, fast.", "recent_news": "", **over}


def test_notes_text_includes_sections_and_skips_empty_news():
    txt = _notes_text(_res())
    assert "What they do" in txt and "A fintech." in txt
    assert "Recent news" not in txt   # empty news omitted


def test_notes_no_longer_have_how_you_fit():
    assert "How you fit" not in _notes_text(_res())
    assert "how_liam_fits" not in RESEARCH_SCHEMA["properties"]


def test_notes_say_when_site_was_not_read():
    assert "website wasn't read" in _notes_text(_res(), site_read=False)
    assert "website wasn't read" not in _notes_text(_res(), site_read=True)


def test_website_from_ashby_page_data():
    html = '<script>window.__appData = {"organization":{"publicWebsite":"https://acme.com/"}};</script>'
    assert website_url(html, "") == "https://acme.com/"


def test_website_from_careers_url_root():
    assert website_url("", "https://acme.com/careers/open") == "https://acme.com/"


def test_hiring_tool_host_is_not_a_company_site():
    assert website_url("", "https://jobs.ashbyhq.com/acme") == ""
    assert website_url("", "https://boards.greenhouse.io/acme") == ""


def test_no_information_means_no_website():
    assert website_url("", "") == ""


class _Client:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url):
        self.asked.append(url)
        if url not in self.pages:
            raise PermissionError("robots.txt disallows")
        return type("R", (), {"text": self.pages[url]})()


def test_site_text_reads_the_website():
    client = _Client({"https://acme.com/": "<p>We build rockets.</p>"})
    assert read_site(client, "https://acme.com/") == "We build rockets."


def test_a_robots_refusal_counts_as_not_read():
    assert read_site(_Client({}), "https://acme.com/") == ""


def test_no_url_makes_no_request():
    client = _Client({})
    assert read_site(client, "") == "" and client.asked == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} researcher tests passed.")
