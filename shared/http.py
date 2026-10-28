"""Polite, rate-limited HTTP for all source fetching.

Enforces the brief's "respect sites" rule in one place:
- an honest User-Agent that identifies the project,
- ~1 request/second per host,
- retry with backoff on 429 / 5xx,
- robots.txt respect (cached per host; fetch failures are treated as allowed).
"""

from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "liams-agents/1.0 (+https://github.com/Liamhasson/liams-agents)"
DEFAULT_MIN_INTERVAL = 1.0  # seconds between requests to the same host


class PoliteClient:
    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL, timeout: float = 30.0):
        self.min_interval = min_interval
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- politeness -----------------------------------------------------
    def _throttle(self, host: str) -> None:
        now = time.monotonic()
        last = self._last.get(host)
        if last is not None:
            wait = self.min_interval - (now - last)
            if wait > 0:
                time.sleep(wait)
        self._last[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                r = self._http.get(f"{urlparse(url).scheme}://{host}/robots.txt")
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:
                    rp = None  # no robots / not found -> allowed
            except Exception:
                rp = None
            self._robots[host] = rp
        rp = self._robots[host]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    # ---- fetching -------------------------------------------------------
    def get(self, url: str, *, check_robots: bool = True, retries: int = 4) -> httpx.Response:
        if check_robots and not self._allowed(url):
            raise PermissionError(f"robots.txt disallows fetching {url}")
        host = urlparse(url).netloc
        for attempt in range(retries):
            self._throttle(host)
            r = self._http.get(url)
            if r.status_code == 429 or r.status_code >= 500:
                backoff = float(r.headers.get("Retry-After", 2 ** attempt))
                time.sleep(min(backoff, 30))
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"GET {url} failed after {retries} attempts (last status {r.status_code})")
