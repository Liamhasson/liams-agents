"""Parser unit tests for every Hunter adapter — fixtures only, no network."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hunter.sources import (
    greenhouse, lever, ashby, workable, recruitee, personio,
    rss, arbeitnow, remotive, remoteok,
)


class FakeResponse:
    def __init__(self, json_data=None, text=""):
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


class FakeClient:
    """Returns a fixed response for any .get(), ignoring the URL."""
    def __init__(self, json_data=None, text=""):
        self._resp = FakeResponse(json_data, text)

    def get(self, url, **kwargs):
        return self._resp


def test_greenhouse():
    c = FakeClient(json_data={"jobs": [{
        "id": 1, "title": "Product Designer",
        "location": {"name": "Berlin"}, "absolute_url": "http://x",
        "updated_at": "2026-01-01T00:00:00Z", "content": "<p>hello</p>",
    }]})
    jobs = greenhouse.fetch(c, "acme", "Acme")
    j = jobs[0]
    assert j.ats == "greenhouse" and j.job_id == "1" and j.company == "Acme"
    assert j.dedupe_key == "greenhouse:acme:1"
    assert j.remote == "" and "hello" in j.description


def test_lever_detects_remote():
    c = FakeClient(json_data=[{
        "id": "abc", "text": "UX Designer", "categories": {"location": "Remote"},
        "hostedUrl": "h", "applyUrl": "a", "descriptionPlain": "d",
    }])
    j = lever.fetch(c, "acme", "Acme")[0]
    assert j.ats == "lever" and j.job_id == "abc" and j.remote == "yes"


def test_ashby_is_remote_flag():
    c = FakeClient(json_data={"jobs": [{
        "id": "x", "title": "Brand Designer", "location": "Berlin",
        "isRemote": True, "jobUrl": "j", "applyUrl": "a",
        "publishedAt": "2026-01-01", "descriptionPlain": "d",
    }]})
    j = ashby.fetch(c, "acme", "Acme")[0]
    assert j.remote == "yes" and j.dedupe_key == "ashby:acme:x"


def test_workable_telecommuting():
    c = FakeClient(json_data={"name": "Acme", "jobs": [{
        "title": "Designer", "shortcode": "SC1", "application_url": "u",
        "location": {"city": "Berlin", "country": "DE", "telecommuting": True},
        "created_at": "2026-01-01", "description": "<b>d</b>",
    }]})
    j = workable.fetch(c, "acme")[0]
    assert j.company == "Acme" and j.job_id == "SC1" and j.remote == "yes"


def test_recruitee():
    c = FakeClient(json_data={"offers": [{
        "id": 5, "title": "UI Designer", "city": "Berlin", "country": "DE",
        "careers_url": "c", "careers_apply_url": "ca", "description": "d", "remote": False,
    }]})
    j = recruitee.fetch(c, "acme", "Acme")[0]
    assert j.ats == "recruitee" and j.job_id == "5" and j.location == "Berlin, DE"


def test_personio_xml():
    xml = (
        '<?xml version="1.0"?><workzag-jobs><position>'
        "<id>7</id><name>Product Designer</name><office>Berlin</office>"
        "<jobDescriptions><jobDescription><name>desc</name><value>Hello world</value>"
        "</jobDescription></jobDescriptions><createDate>2026-01-01</createDate>"
        "</position></workzag-jobs>"
    )
    c = FakeClient(text=xml)
    j = personio.fetch(c, "acme", "Acme")[0]
    assert j.job_id == "7" and "/job/7" in j.url and "Hello world" in j.description


def test_rss_at_style():
    xml = ("<rss><channel><item><title>UX Designer at Acme</title>"
           "<link>http://x</link><description>remote role</description>"
           "<guid>g1</guid></item></channel></rss>")
    j = rss.fetch(FakeClient(text=xml), "http://feed", "SomeFeed", style="at")[0]
    assert j.title == "UX Designer" and j.company == "Acme" and j.remote == "yes"


def test_rss_colon_style():
    xml = ("<rss><channel><item><title>Acme: UI Designer</title>"
           "<link>http://x</link><description>d</description></item></channel></rss>")
    j = rss.fetch(FakeClient(text=xml), "http://feed", "WWR", style="colon")[0]
    assert j.title == "UI Designer" and j.company == "Acme"


def test_arbeitnow():
    c = FakeClient(json_data={"data": [{
        "title": "Designer", "company_name": "Acme", "url": "u",
        "location": "Berlin", "remote": True, "slug": "s1", "description": "<p>d</p>",
    }]})
    j = arbeitnow.fetch(c)[0]
    assert j.company == "Acme" and j.remote == "yes" and j.source == "Arbeitnow"


def test_remotive_attribution():
    c = FakeClient(json_data={"jobs": [{
        "id": 9, "title": "Designer", "company_name": "Acme", "url": "u",
        "candidate_required_location": "EU", "publication_date": "2026-01-01",
        "description": "<p>d</p>",
    }]})
    j = remotive.fetch(c)[0]
    assert j.company == "Acme" and "Remotive" in j.source and "remotive.com" in j.source


def test_remoteok_skips_legal_notice():
    c = FakeClient(json_data=[
        {"legal": "attribution notice"},  # leading object, must be skipped
        {"id": "1", "position": "Designer", "company": "Acme", "url": "u",
         "description": "d", "date": "2026-01-01"},
    ])
    jobs = remoteok.fetch(c)
    assert len(jobs) == 1 and jobs[0].company == "Acme" and "RemoteOK" in jobs[0].source


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Hunter parser tests passed.")
