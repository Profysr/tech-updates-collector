"""collectors/hn.py — Hacker News via Algolia API (10k req/hr keyless [V])."""
from util import json_get, make_item

BASE = "https://hn.algolia.com/api/v1/search_by_date"


def _collect(url: str, source: str) -> list[dict]:
    data = json_get(url)
    out = []
    for hit in data.get("hits", []):
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        eng = f"{hit.get('points', 0)} pts / {hit.get('num_comments', 0)} comments"
        out.append(make_item(source, hit.get("title") or "(untitled)", link,
                             engagement=eng, published=hit.get("created_at", "")))
    return out


def collect_front_page(limit: int = 20) -> list[dict]:
    return _collect(f"{BASE}?tags=front_page&hitsPerPage={limit}", "hn.front_page")


def collect_show_hn(limit: int = 20) -> list[dict]:
    return _collect(f"{BASE}?tags=show_hn&hitsPerPage={limit}", "hn.show_hn")
