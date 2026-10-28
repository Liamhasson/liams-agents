"""Pure unit tests for the dedupe logic — no network, always runnable."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.models import Job


def test_title_company_hash_is_stable_across_cosmetic_differences():
    a = Job(title="Product Designer", company="Acme GmbH")
    b = Job(title="  product   designer ", company="ACME  GmbH!")
    assert a.title_company_hash == b.title_company_hash


def test_different_jobs_have_different_hashes():
    a = Job(title="Product Designer", company="Acme")
    b = Job(title="UX Researcher", company="Acme")
    assert a.title_company_hash != b.title_company_hash


def test_dedupe_key_prefers_ats_triple():
    job = Job(title="X", company="Y", ats="greenhouse", company_slug="acme", job_id="42")
    assert job.dedupe_key == "greenhouse:acme:42"


def test_dedupe_key_falls_back_to_hash_without_triple():
    job = Job(title="X", company="Y")
    assert job.dedupe_key.startswith("hash:")
    assert job.dedupe_key == f"hash:{job.title_company_hash}"


def test_same_posting_different_source_dedupes_by_hash():
    # Same job seen on two boards with no stable ATS id -> same fallback key.
    linkedin = Job(title="Senior Product Designer", company="Blinkist", source="linkedin")
    board = Job(title="senior product designer", company="blinkist", source="berlinstartupjobs")
    assert linkedin.dedupe_key == board.dedupe_key


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} dedupe unit tests passed.")
