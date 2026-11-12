"""util.py — stdlib-only helpers: HTTP with retry, timestamps, logging.

Rules (errata §4.3): tokens optional via env -> keyring -> .env (setup.py
writes .env); failed source logs "unknown coverage", never "no
news"; watermarks advance only on success.
"""
from __future__ import annotations

import email.utils
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

USER_AGENT = "tech-trends-collector/0.1 (personal research; keyless)"
DEFAULT_TIMEOUT = 30


# Shared, pooled client: connection reuse across retries/calls.
_client = httpx.Client(
    headers={"User-Agent": USER_AGENT},
    timeout=httpx.Timeout(DEFAULT_TIMEOUT),
    follow_redirects=True,
)


def http_get(url: str, headers: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
             retries: int = 2, backoff: float = 2.0) -> str:
    """GET with retry + exponential backoff. Raises on final failure (caller
    turns it into a coverage gap)."""
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = _client.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except (httpx.HTTPError, OSError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise ConnectionError(f"GET {url} failed after {retries + 1} attempts: {last_err}")


def json_get(url: str, headers: dict | None = None) -> dict | list:
    return json.loads(http_get(url, headers))


def post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    """POST a JSON body (urllib, 30s) — GETs go through http_get/json_get."""
    import urllib.request
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


# Keyring service name for all tech-updates tokens.
KEYRING_SERVICE = "tech-updates"


def _from_keyring(env_var: str) -> str:
    """Token from the OS keyring (fail soft: any backend error -> '')."""
    try:
        import keyring
        return (keyring.get_password(KEYRING_SERVICE, env_var) or "").strip()
    except Exception:  # noqa: BLE001 — no backend / locked keyring: next source
        return ""


def _from_dotenv(env_var: str) -> str:
    """Token from the package's ``.env`` file (fail soft: any error -> '')."""
    try:
        from dotenv import dotenv_values
        env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
        return (env.get(env_var) or "").strip()
    except Exception:  # noqa: BLE001 — no python-dotenv / unreadable file
        return ""


def optional_token(env_var: str) -> str | None:
    """Token lookup chain: environment variable -> keyring -> ``.env`` file.

    Hermes' cron subprocess env sanitizer strips credential env vars
    (GITHUB_TOKEN is Tier-1), so keyring/.env are the reliable paths under
    the gateway. Every source may fail (headless host without a keyring
    backend, missing .env) — never required, never crashes the run."""
    for fetch in (os.environ.get(env_var, "").strip, lambda: _from_keyring(env_var),
                  lambda: _from_dotenv(env_var)):
        try:
            val = fetch()
        except Exception:  # noqa: BLE001 — lookup must never crash
            val = ""
        if val:
            return val
    return None


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
