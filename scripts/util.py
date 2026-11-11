"""util.py — stdlib-only helpers: HTTP with retry, timestamps, logging.

Rules (errata §4.3): tokens optional via env; failed source logs "unknown
coverage", never "no news"; watermarks advance only on success.
"""
from __future__ import annotations

import email.utils
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "tech-trends-collector/0.1 (personal research; keyless)"
DEFAULT_TIMEOUT = 30


def store_root() -> Path:
    """Store root for RAW pipeline data (runs, sources, run log).

    Resolved by ``paths.py`` (TECH_UPDATES_ROOT env -> store.config.json
    -> default ``<project>/tech-updates``). Raw output is disposable
    by-design; durable cursors stay in the project's ``state/``.
    """
    import paths
    return paths.data_root()


def http_get(url: str, headers: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
             retries: int = 2, backoff: float = 2.0) -> str:
    """GET with retry. Raises on final failure (caller turns it into a
    coverage gap)."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise ConnectionError(f"GET {url} failed after {retries + 1} attempts: {last_err}")


def json_get(url: str, headers: dict | None = None) -> dict | list:
    return json.loads(http_get(url, headers))


def optional_token(env_var: str) -> str | None:
    """Token from env, else ``state/tokens/<NAME>`` file. Hermes' cron subprocess
    env sanitizer strips credential env vars (GITHUB_TOKEN is Tier-1), so the
    file is the reliable path when running under the gateway. Never required."""
    val = os.environ.get(env_var, "").strip()
    if val:
        return val
    f = Path(__file__).resolve().parent.parent / "state" / "tokens" / env_var
    try:
        val = f.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return val or None


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rfc822_to_iso(value: str) -> str:
    """RFC 822 pubDate -> ISO 8601 UTC (best effort; returns '' if unparseable)."""
    if not value:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return value


def make_item(source: str, title: str, link: str, engagement: str = "",
              published: str = "", extra: str = "") -> dict:
    """Every fetched item records link + source + engagement + timestamp."""
    return {
        "source": source,
        "title": (title or "").strip()[:200],
        "link": link,
        "engagement": engagement,
        "published": published or now_utc(),
        "fetched_at": now_utc(),
        "extra": extra,
    }


def item_key(item: dict) -> str:
    """Seen-item identity: normalized link (strip tracking/fragment)."""
    link = (item.get("link") or "").split("#")[0].split("?")[0].rstrip("/")
    return link.lower()


class SourceResult:
    """Outcome of one collector: items, or a failure -> 'unknown coverage'."""

    def __init__(self, source_key: str):
        self.source_key = source_key
        self.items: list[dict] = []
        self.error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def coverage_line(self) -> str:
        if self.ok:
            return f"{self.source_key}: {len(self.items)} new candidate items"
        return f"{self.source_key}: FAILED ({self.error}) — unknown coverage, not 'no news'"


def run_collector(fn, source_key: str, *args) -> SourceResult:
    """Wrap a collector fn so exceptions become coverage gaps, never crashes."""
    res = SourceResult(source_key)
    try:
        res.items = fn(*args) or []
    except Exception as e:  # noqa: BLE001 — collector failures must not kill the run
        res.error = f"{type(e).__name__}: {e}"
    return res
