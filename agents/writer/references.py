"""Use Liam's approved letters and CVs when drafting (docs/workplan-writer-learns.md, step 4).

The closest references (by company, role and role type, newest first) go into the
final-draft prompt. Their story paragraphs may be reused word for word when the
facts still fit; openings and closings are never passed on, so they're always
written fresh. Sentences copied word for word are Liam's own approved words: the
style lint skips them, and Liam is told what was reused.
"""

from __future__ import annotations

import re

from .context import Reference, WriterContext
from .learn import split_units

_GREETING = re.compile(r"^(hi|hello|dear|hey)\b", re.I)
_STOP = {"and", "the", "for", "with", "of", "a", "an", "in", "at", "to", "or", "role", "unknown"}


def _words(*texts: str) -> set[str]:
    return {w for t in texts for w in re.findall(r"[a-z]+", t.lower()) if len(w) > 2 and w not in _STOP}


def score(ref: Reference, ctx: WriterContext) -> int:
    same_company = ref.company.strip().lower() == ctx.company.strip().lower() and ctx.company.strip()
    return 5 * bool(same_company) + len(_words(ref.role, ref.role_type) & _words(ctx.title, ctx.role_type))


def pick(ctx: WriterContext, letters: int = 2, cvs: int = 1) -> list[Reference]:
    """The closest approved letters and CVs; newest first among equals."""
    ranked = sorted(ctx.references, key=lambda r: (score(r, ctx), r.approved), reverse=True)
    return ([r for r in ranked if r.kind == "cover letter"][:letters]
            + [r for r in ranked if r.kind == "CV"][:cvs])


def story_paragraphs(letter: str) -> list[str]:
    """A letter's middle: no greeting, no opening paragraph, no closing line, no sign-off."""
    paras: list[str] = []
    for p in (p.strip() for p in re.split(r"\n\s*\n", letter)):
        if paras and re.fullmatch(r"https?://\S+", p):  # a link on its own line belongs to its paragraph
            paras[-1] += "\n" + p
        elif p:
            paras.append(p)
    if paras and _GREETING.match(paras[0]) and len(paras[0]) < 80:
        paras = paras[1:]
    if paras and len(paras[-1]) < 40:  # "Thanks, Liam"
        paras = paras[:-1]
    return paras[1:-1]  # drop the opening and the closing invitation


def block(refs: list[Reference], kind: str | None = None) -> str:
    """Prompt text for the picked references. `kind` limits it to letters or CVs."""
    parts = []
    for r in refs:
        if kind and r.kind != kind:
            continue
        head = f"[{r.title}: {r.role} at {r.company}, approved {r.approved}]"
        if r.kind == "CV":
            parts.append(f"{head}\n{r.text}")
        else:
            paras = story_paragraphs(r.text)
            if paras:
                parts.append(f"{head}\nStory paragraphs:\n\n" + "\n\n".join(paras))
    return "\n\n".join(parts)


def approved_sentences(refs: list[Reference], kind: str) -> set[str]:
    """Every sentence (letters) or line (CVs) Liam approved, for exact-match checks."""
    return {u for r in refs if r.kind == kind for u in split_units(r.text, kind) if len(u) > 25}


def without_approved(text: str, refs: list[Reference], kind: str) -> str:
    """Drop sentences copied word for word from approved references (his words win over the lint)."""
    approved = approved_sentences(refs, kind)
    return "\n\n".join(u for u in split_units(text, kind) if u not in approved)


def reused(text: str, refs: list[Reference], kind: str) -> dict[str, int]:
    """{reference title: sentences copied word for word} so Liam can see what was reused."""
    units = set(split_units(text, kind))
    out = {}
    for r in refs:
        if r.kind != kind:
            continue
        n = sum(1 for u in split_units(r.text, kind) if len(u) > 25 and u in units)
        if n:
            out[r.title] = n
    return out
