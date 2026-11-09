"""Check that a quote really appears in its source.

The agents may only state something if they can show the words it came from.
A model can make up a quote as easily as a claim, so code does the checking.
"""

from __future__ import annotations

import re

_CURLY = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_CURLY).lower()).strip()


def appears_in(quote: str, source: str, min_chars: int = 8) -> bool:
    """True if `quote` is in `source`, ignoring case, quote style, spacing and closing punctuation."""
    wanted = _norm(quote).rstrip(".,;:!?\"' ")
    return len(wanted) >= min_chars and wanted in _norm(source)
