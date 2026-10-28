"""Runtime configuration.

Secrets load from a local .env during development and from real environment
variables in CI (GitHub Actions). Nothing secret is ever hard-coded here.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present (local dev). In CI the vars are already in the environment,
# so override=False means real env vars win.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_ROOT_PAGE_ID = os.environ.get("NOTION_ROOT_PAGE_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def require(name: str) -> str:
    """Return a required env var or raise a clear error naming what's missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Add it to your local .env or to GitHub Actions secrets."
        )
    return value
