"""collectors/chatter.py — Reddit RSS (RSS only), dev.to, Lobsters, vendor RSS."""
import urllib.parse

from collectors.feeds import collect_rss

REDDIT_FEEDS = {
    "reddit.rLocalLLaMA": "https://www.reddit.com/r/LocalLLaMA/.rss",
    "reddit.rClaudeAI": "https://www.reddit.com/r/ClaudeAI/.rss",
    "reddit.rMachineLearning": "https://www.reddit.com/r/MachineLearning/.rss",
    "reddit.rProgramming": "https://www.reddit.com/r/programming/.rss",
}
VENDOR_FEEDS = {
    # anthropic.com has no discoverable RSS (404 on /rss.xml, /feed.xml, /blog/rss.xml)
    # — anthropic updates stay covered via github.releases.anthropics/* until the
    # deferred sitemap-lastmod collector lands (errata §5).
    "vendor.openai": "https://openai.com/news/rss.xml",
}
OTHER_FEEDS = {
    "lobsters": "https://lobste.rs/rss",
}


def collect_reddit(limit: int = 10) -> list[dict]:
    """Reddit RSS only — keyless *.json is blocked [verified]. Anonymous throttle
    is ~1 req/min per IP, so each run fetches ONE feed, rotating by wall-clock
    minute; all four subs cycle across consecutive runs."""
    import time
    keys = sorted(REDDIT_FEEDS)
    idx = int(time.time() // 60) % len(keys)
    key = keys[idx]
    return collect_rss(key, REDDIT_FEEDS[key], limit)


def collect_vendors(limit: int = 10) -> list[dict]:
    out = []
    for key, url in VENDOR_FEEDS.items():
        out += collect_rss(key, url, limit)
    return out


def collect_other(limit: int = 15) -> list[dict]:
    out = []
    for key, url in OTHER_FEEDS.items():
        out += collect_rss(key, url, limit)
    data = json_get_devto(limit)
    for a in data:
        out.append({
            "source": "devto.top7",
            "title": (a.get("title") or "").strip()[:200],
            "link": a.get("url") or a.get("path", ""),
            "engagement": f"{a.get('positive_reactions_count', 0)} reactions / {a.get('comments_count', 0)} comments",
            "published": a.get("published_at", ""),
            "fetched_at": "",
            "extra": "",
        })
    return [i for i in out if i["link"]]


def json_get_devto(limit: int):
    from util import json_get
    return json_get(f"https://dev.to/api/articles?top=7&per_page={limit}")


def reddit_search_feed(subreddit: str, query: str) -> str:
    return f"https://www.reddit.com/search.rss?q={urllib.parse.quote(query)}&sort=new"
