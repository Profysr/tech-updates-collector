"""collectors/adoption.py — PyPI RSS + npm download counts for watchlist packages."""
from collectors.feeds import collect_rss
from util import json_get, make_item

PYPI_FEEDS = {
    "pypi.updates": "https://pypi.org/rss/updates.xml",
    "pypi.packages": "https://pypi.org/rss/packages.xml",
}


def collect_pypi(limit: int = 15) -> list[dict]:
    out = []
    for key, url in PYPI_FEEDS.items():
        out += collect_rss(key, url, limit)
    return out


def collect_npm(packages: list[str]) -> list[dict]:
    """Weekly download counts for watchlist packages (adoption velocity input)."""
    out = []
    for pkg in packages:
        data = json_get(f"https://api.npmjs.org/downloads/point/last-week/{pkg}")
        out.append(make_item(
            "npm.downloads", f"npm: {pkg}", f"https://www.npmjs.com/package/{pkg}",
            engagement=f"{data.get('downloads', '?')} downloads/week",
            extra="watchlist package — recorded for momentum deltas"))
    return out
