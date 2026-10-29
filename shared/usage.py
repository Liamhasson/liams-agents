"""Usage log and monthly limit for the agents' Claude calls (BUILD_BRIEF §15).

Every run that used Claude adds one row to the Notion "Usage" database. The
monthly limit (config/settings.yaml > usage) is on the API-equivalent value, so
it means the same whether the agents run on the subscription or the API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import config
from .claude import Claude
from .notion import NotionClient
from .notion.client import plain_number, plain_select

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


def _cfg() -> dict:
    return yaml.safe_load(_CONFIG.read_text()).get("usage", {})


def limit_usd() -> float:
    return float(_cfg().get("monthly_limit_usd", 15))


def month_total(notion: NotionClient, now: datetime | None = None) -> tuple[float, dict[str, float]]:
    """API-equivalent $ used this calendar month: (total, per agent)."""
    now = now or datetime.now(timezone.utc)
    rows = notion.query_database(notion.ensure_databases()["Usage"], {
        "property": "Date", "date": {"on_or_after": now.strftime("%Y-%m-01")}})
    per: dict[str, float] = {}
    for r in rows:
        agent = plain_select(r, "Agent") or "other"
        per[agent] = per.get(agent, 0.0) + (plain_number(r, "API-equivalent $") or 0.0)
    return sum(per.values()), per


def over_limit(notion: NotionClient) -> bool:
    return month_total(notion)[0] >= limit_usd()


def crossed(before: float, after: float, limit: float, warn_at: float) -> str | None:
    """Which threshold this run crossed, if any: 'limit', 'warn' or None."""
    if before < limit <= after:
        return "limit"
    if before < limit * warn_at <= after:
        return "warn"
    return None


def warning_text(kind: str, total: float, limit: float) -> str:
    if kind == "limit":
        return (f"⛔ The agents reached this month's usage limit (${total:.2f} of ${limit:.0f} "
                "API-equivalent). Matching and research are paused until next month. The Hunter "
                "keeps collecting jobs, and the Writer still works when you start it. To raise the "
                "limit, change usage › monthly_limit_usd in config/settings.yaml.")
    return (f"⚠️ The agents have used {total / limit:.0%} of this month's limit "
            f"(${total:.2f} of ${limit:.0f} API-equivalent).")


def log_run(notion: NotionClient, claude: Claude, agent: str) -> None:
    """Add this run's usage to Notion and warn on Telegram when it crosses a threshold."""
    if not claude.calls:
        return
    before, _ = month_total(notion)
    now = datetime.now(timezone.utc)
    notion.create_page(notion.ensure_databases()["Usage"], {
        "Run": {"title": [{"text": {"content": f"{agent} {now:%Y-%m-%d %H:%M}"}}]},
        "Date": {"date": {"start": now.isoformat()}},
        "Agent": {"select": {"name": agent}},
        "Backend": {"select": {"name": claude.backend}},
        "Model": {"rich_text": [{"text": {"content": claude.model}}]},
        "Calls": {"number": claude.calls},
        "Input tokens": {"number": claude.input_tokens},
        "Output tokens": {"number": claude.output_tokens},
        "API-equivalent $": {"number": round(claude.cost_usd, 4)},
    })
    kind = crossed(before, before + claude.cost_usd, limit_usd(), float(_cfg().get("warn_at", 0.8)))
    if kind:
        from .telegram import Telegram
        Telegram().send_message(config.require("TELEGRAM_CHAT_ID"),
                                warning_text(kind, before + claude.cost_usd, limit_usd()))
