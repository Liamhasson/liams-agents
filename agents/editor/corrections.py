"""Save Liam's corrections to his voice guide, silently and in his own words.

The guide also counts as proof in the fact check, so nothing goes in unless code
can find the words in what he wrote or in the draft he corrected. The model never
writes why he changed something.
"""

from __future__ import annotations

from typing import Optional

from shared.quotes import appears_in
from . import learn
from .mytone import append_correction

_MIN = 3  # corrections can be short, like "shorter"


def entry(action: dict, message: str, asset_before: str, tag: str) -> Optional[str]:
    """The line to save, or None if the words aren't really his."""
    form, old = action.get("correction_form"), action.get("old_line", "")
    words = action.get("liams_words", "")
    if form == "wording":
        new = action.get("new_line", "")
        if appears_in(new, message, _MIN) and appears_in(old, asset_before, _MIN):
            return f'[{tag}] Instead of "{old}", Liam wrote "{new}".'
    elif form == "instruction" and appears_in(words, message, _MIN):
        if not old:
            return f'[{tag}] Liam said: "{words}".'
        if appears_in(old, asset_before, _MIN):
            return f'[{tag}] About "{old}", Liam said: "{words}".'
    elif form == "fact_or_rule" and appears_in(words, message, _MIN):
        return f'[{tag}] Liam said: "{words}".'
    return None


def save(notion, action: dict, message: str, asset_before: str, tag: str) -> Optional[str]:
    """Write the correction to the guide. Returns the line written, or None if there was nothing to save."""
    never = action.get("never_line", "")
    if never and (appears_in(never, asset_before, _MIN) or appears_in(never, message, _MIN)):
        learn.add_never_again(notion, never, "Liam said never to use this.", "shared", tag)
    line = entry(action, message, asset_before, tag)
    if line:
        append_correction(notion, line)
    return line
