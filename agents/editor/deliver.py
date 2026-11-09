"""Send one finished asset to Liam, in the form he'll use it."""

from __future__ import annotations

import html
import json
from pathlib import Path

from modules.pdf.generator import generate_cover_letter_pdf, generate_cv_pdf
from shared.assets import Asset
from .context import EditorContext

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"
_LIMIT = 4000  # Telegram's cap is 4,096
_ANSWER_LIMIT = 3500  # leaves room for the question and <code> tags


def split_message(text: str, limit: int = _LIMIT) -> list[str]:
    """Break long text on paragraph breaks so nothing is cut. A paragraph over the limit is split by length."""
    parts: list[str] = []
    current = ""
    for para in (text or "").split("\n\n"):
        while len(para) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(para[:limit])
            para = para[limit:]
        joined = f"{current}\n\n{para}" if current else para
        if len(joined) > limit:
            parts.append(current)
            current = para
        else:
            current = joined
    if current:
        parts.append(current)
    return parts


def safe_parts(text: str, limit: int = _LIMIT) -> list[str]:
    """Split, then escape for Telegram, so an entity like &amp; is never cut in half."""
    out: list[str] = []
    for part in split_message(text, limit):
        escaped = html.escape(part, quote=False)
        if len(escaped) <= limit:
            out.append(escaped)
        else:
            middle = len(part) // 2
            out += safe_parts(part[:middle], limit) + safe_parts(part[middle:], limit)
    return out


def _slug(ctx: EditorContext) -> str:
    return ctx.company.replace(" ", "_").replace("/", "-")[:30] or "job"


def deliver(tg, chat, ctx: EditorContext, asset: Asset) -> None:
    if asset.kind in ("cv", "cover_letter"):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if asset.kind == "cv":
            path = generate_cv_pdf(asset.text, OUTPUT_DIR / f"{_slug(ctx)}_cv.pdf")
        else:
            path = generate_cover_letter_pdf(asset.text, OUTPUT_DIR / f"{_slug(ctx)}_cover.pdf", cv_markdown=ctx.base_cv)
        tg.send_document(chat, str(path), caption=f"{asset.label}, {ctx.company}")
    elif asset.kind == "form_answers":
        for item in json.loads(asset.text):
            question = html.escape(item["question"], quote=False)
            if item["answer"].strip():
                for i, part in enumerate(safe_parts(item["answer"], _ANSWER_LIMIT)):
                    tg.send_message(chat, f"<b>{question}</b>\n<code>{part}</code>" if i == 0 else f"<code>{part}</code>")
            else:
                tg.send_message(chat, f"<b>{question}</b>\nOnly you can answer this one. It isn't in your CV or voice guide.")
    else:
        for part in safe_parts(asset.text):
            tg.send_message(chat, part)
