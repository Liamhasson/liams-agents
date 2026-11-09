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
                answer = html.escape(item["answer"], quote=False)
                tg.send_message(chat, f"<b>{question}</b>\n<code>{answer}</code>")
            else:
                tg.send_message(chat, f"<b>{question}</b>\nOnly you can answer this one. It isn't in your CV or voice guide.")
    else:
        for part in split_message(html.escape(asset.text, quote=False)):
            tg.send_message(chat, part)
