"""collectors/feeds.py — generic RSS/Atom reader (feedparser).

Used for Reddit RSS (RSS only — keyless *.json is blocked), vendor RSS,
Lobsters, SO, PyPI.
"""
import calendar

import feedparser

from util import http_get, make_item, rfc822_to_iso


def _struct_to_iso(ts) -> str:
    """time.struct_time from feedparser -> ISO 8601 UTC ('' if None)."""
    from datetime import datetime, timezone
    if not ts:
        return ""
    return datetime.fromtimestamp(calendar.timegm(ts), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _entry_link(e) -> str:
    for l in e.get("links", []):
        if l.get("href") and l.get("rel", "alternate") == "alternate":
            return l["href"]
    return e.get("link") or e.get("id") or ""


def parse_feed(xml: str) -> list[tuple[str, str, str]]:
    """-> [(title, link, published_iso)]"""
    out = []
    for e in feedparser.parse(xml).entries:
        title = e.get("title", "")
        link = _entry_link(e)
        pub = _struct_to_iso(e.get("published_parsed") or e.get("updated_parsed"))
        if not pub:
            pub = rfc822_to_iso(e.get("published") or e.get("updated") or "")
        out.append((title, link, pub))
    return out


def collect_rss(source_key: str, url: str, limit: int = 20) -> list[dict]:
    xml = http_get(url)
    out = []
    for title, link, pub in parse_feed(xml)[:limit]:
        out.append(make_item(source_key, title, link, published=pub))
    return out
