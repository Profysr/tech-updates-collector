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

from util import http_get, make_item

HOME = "https://trendshift.io/"


def collect() -> list[dict]:
    """Homepage leaderboard: repos in daily-trend order (deduped)."""
    html = http_get(HOME)
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'github\.com/([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+)', html):
        repo = m.group(1).rstrip("/")
        if repo in seen or repo.count("/") != 1 or repo.startswith(("features", "docs")):
            continue
        seen.add(repo)
        out.append(make_item("trendshift.repos", repo, f"https://github.com/{repo}",
                             extra="trendshift.io daily/weekly trending"))
    if not out:
        raise ValueError("trendshift.io: no repos parsed from homepage (layout changed?)")
    return out[:30]
