"""The quote check: a claim only counts if its words really appear in the source."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.quotes import appears_in


def test_exact_quote():
    assert appears_in("Record a Loom", "Please record a loom of your work.")


def test_curly_quotes_and_line_breaks():
    assert appears_in("We don't want your CV first", "We don’t want\nyour   CV first.")


def test_emoji_in_source():
    assert appears_in("portfolio link 🎨 please", "Send a portfolio link 🎨 please!")


def test_invented_quote_rejected():
    assert not appears_in("five years of Figma", "Send a portfolio.")


def test_too_short_rejected():
    assert not appears_in("CV", "Send a CV.")


def test_empty_rejected():
    assert not appears_in("", "text")


def test_trailing_punctuation_is_ignored():
    assert appears_in("Send us your portfolio.", "Send us your portfolio and a short note.")
