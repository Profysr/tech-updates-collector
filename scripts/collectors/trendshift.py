"""collectors/trendshift.py — trendshift.io leaderboard (Group C momentum).

PROBE RESULT (2026-10-21, sources.yaml amendment): https://trendshift.io/repositories
returns HTTP 404 (also ?language=all, /rss, /feed.xml, /api/repositories —
all 404/JS-walled). The homepage https://trendshift.io/ however server-renders
its Daily/Weekly/Monthly repository leaderboard in plain HTML (repo names +
stars present in the response body). This collector therefore scrapes the
homepage leaderboard; /repositories coverage is registered as
blocked_probe_failed in sources.yaml and stays "unknown coverage".
"""
import re

from bs4 import BeautifulSoup

from util import http_get, make_item

HOME = "https://trendshift.io/"


def collect() -> list[dict]:
    """Homepage leaderboard: repos in daily-trend order (deduped)."""
    html = http_get(HOME)
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="github.com/"]'):
        href = (a.get("href") or "").split("github.com/", 1)[1]
        path = href.split("?", 1)[0].split("#", 1)[0].strip("/")
        parts = path.split("/")
        repo = "/".join(parts[:2]) if len(parts) >= 2 and parts[0] and parts[1] else ""
        if not repo:
            continue
        if repo in seen or repo.startswith(("features", "docs")):
            continue
        seen.add(repo)
        out.append(make_item("trendshift.repos", repo, f"https://github.com/{repo}",
                             extra="trendshift.io daily/weekly trending"))
    if not out:
        raise ValueError("trendshift.io: no repos parsed from homepage (layout changed?)")
    return out[:30]
