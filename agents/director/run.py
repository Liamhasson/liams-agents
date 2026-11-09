"""One Director run: started when Liam taps Brief me.

Researcher, then the application form where it's published, then the brief. Liam
reads it whenever he likes, because nothing here needs a live chat.

    python -m agents.director.run --job <id>
    python -m agents.director.run --job <id> --dry-run   # prints the brief, saves and sends nothing
"""

from __future__ import annotations

import argparse
import json
from typing import Callable

from shared import config, usage
from shared.assets import create_assets
from shared.claude import Claude, HAIKU, SONNET
from shared.notion.client import _long_rt, plain_text, plain_title, plain_url
from agents.matcher.asks import extract_asks
from .brief import brief_message, plan_assets, verified_brief, write_brief
from .forms import greenhouse_questions, parse_greenhouse


def _asks(page: dict, haiku, title: str, post: str) -> tuple[list[dict], bool]:
    """The post's asks, and whether they were worked out just now (jobs scored before this existed)."""
    stored = plain_text(page, "Application asks")
    if stored:
        return json.loads(stored), False
    return extract_asks(haiku, title, post), True


def _form(page: dict, http):
    found = parse_greenhouse(plain_text(page, "Source"), plain_url(page, "URL") or plain_url(page, "Apply URL"))
    return greenhouse_questions(http, *found) if found else None


def _brief(job_id, *, notion, tg, chat, ids, sonnet, haiku, http, research, sources, dry_run) -> dict:
    jid = job_id.replace("-", "")
    result = research(job_id)
    page = notion.get_page(job_id)
    job_id = page["id"]  # the webhook passes it without dashes; other tables key on Notion's own form
    title, company, post = plain_title(page), plain_text(page, "Company"), plain_text(page, "Description")
    notes = (result or {}).get("notes") or plain_text(page, "Research notes")

    asks, extracted = _asks(page, haiku, title, post)
    form = _form(page, http)
    cv, mytone = sources(notion)
    raw = write_brief(sonnet, title=title, company=company, post=post, research=notes, cv=cv, mytone=mytone)
    brief = verified_brief(raw, cv, mytone, post=post)
    planned = plan_assets(asks, form)
    text, buttons = brief_message(brief, planned, form is not None, jid, title, company)

    if dry_run:
        return {"text": text, "buttons": buttons, "dropped_points": len(raw.get("why_you", [])) - len(brief["why_you"])}

    props = {"Director brief": _long_rt(text)}
    if extracted:
        props["Application asks"] = _long_rt(json.dumps(asks, ensure_ascii=False))
    if form is not None:
        props["Form questions"] = _long_rt(json.dumps(form, ensure_ascii=False))
    notion.update_page(job_id, props)
    create_assets(notion, ids["Assets"], job_id, planned)
    sent = tg.send_message(chat, text, buttons)
    notion.update_page(job_id, {"Status": {"select": {"name": "Briefed"}},
                                "Brief message id": {"number": sent["message_id"]}})
    return {"briefed": 1}


def brief_job(job_id: str, *, notion, tg, chat, ids: dict, sonnet, haiku, http, research: Callable,
              sources: Callable, dry_run: bool = False) -> dict:
    """Brief Liam on one job. If anything fails he's told, and can try again from the message."""
    if usage.over_limit(notion):
        if not dry_run:
            tg.send_message(chat, "This month's usage limit is reached, so I can't write the brief. "
                                  "It can be raised in config/settings.yaml.")
        return {"paused": True}
    try:
        return _brief(job_id, notion=notion, tg=tg, chat=chat, ids=ids, sonnet=sonnet, haiku=haiku, http=http,
                      research=research, sources=sources, dry_run=dry_run)
    except Exception as e:
        if not dry_run:
            tg.send_message(chat, f"⚠️ Couldn't write the brief: {type(e).__name__}. Nothing is lost.",
                            [[("🔁 Try again", f"brief:{job_id.replace('-', '')}")]])
        raise
    finally:
        usage.log_run(notion, sonnet, "director")
        usage.log_run(notion, haiku, "director")


def run(job_id: str, dry_run: bool = False) -> dict:
    from agents.researcher.run import run as research
    from agents.editor.context import load_base_cv, load_mytone
    from shared.http import PoliteClient
    from shared.notion import NotionClient
    from shared.telegram import Telegram

    notion = NotionClient()
    ids = notion.ensure_databases()
    http = PoliteClient()
    try:
        out = brief_job(job_id, notion=notion, tg=Telegram(), chat=config.require("TELEGRAM_CHAT_ID"), ids=ids,
                        sonnet=Claude(model=SONNET), haiku=Claude(model=HAIKU), http=http,
                        research=lambda j: research(job_id=j, dry_run=dry_run),
                        sources=lambda n: (load_base_cv(n), load_mytone(n)), dry_run=dry_run)
    finally:
        http.close()
    if dry_run and "text" in out:
        print(out["text"])
        print(f"\nButtons: {out['buttons']}\nPoints removed by the quote check: {out['dropped_points']}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Brief Liam on one job")
    ap.add_argument("--job", required=True, help="Notion job page id")
    ap.add_argument("--dry-run", action="store_true", help="print the brief, save and send nothing")
    args = ap.parse_args()
    run(args.job, dry_run=args.dry_run)
