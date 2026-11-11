"""collectors/feeds.py — generic RSS/Atom reader (stdlib regex-based).

Patterns from the rss-feeds skill (stdlib reader). Used for Reddit RSS
(RSS only — keyless *.json is blocked), vendor RSS, Lobsters, SO, PyPI.
"""
import re
from util import http_get, make_item, rfc822_to_iso

ENTRY_RE = re.compile(r"<item>(.*?)</item>|<entry>(.*?)</entry>", re.S | re.I)


def _tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S | re.I)
    if not m:
        return ""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _link(block: str) -> str:
    m = re.search(r"<link[^>]*href=[\"']([^\"']+)[\"']", block, re.I)
    if m:
        return m.group(1)
    m = re.search(r"<link[^>]*>(.*?)</link>", block, re.S | re.I)
    if m:
        return re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", m.group(1)).strip()
    return ""


def parse_feed(xml: str) -> list[tuple[str, str, str]]:
    """-> [(title, link, published_iso)]"""
    out = []
    for m in ENTRY_RE.finditer(xml):
        block = m.group(1) or m.group(2) or ""
        title = _tag(block, "title")
        link = _link(block)
        if not link:
            m2 = re.search(r"<id[^>]*>(.*?)</id>", block, re.I)
            link = re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", m2.group(1)).strip() if m2 else ""
        pub = _tag(block, "pubDate") or _tag(block, "published") or _tag(block, "updated")
        out.append((title, link, rfc822_to_iso(pub)))
    return out


def collect_rss(source_key: str, url: str, limit: int = 20) -> list[dict]:
    xml = http_get(url)
    out = []
    for title, link, pub in parse_feed(xml)[:limit]:
        out.append(make_item(source_key, title, link, published=pub))
    return out
