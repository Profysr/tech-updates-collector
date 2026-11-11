"""collectors/github.py — GitHub REST + Trending scrape + anthropics/skills.

60 req/hr unauth; optional GITHUB_TOKEN lifts to 5,000/hr [verified].
"""
import re
from util import http_get, json_get, make_item, optional_token

API = "https://api.github.com"


def _headers() -> dict:
    tok = optional_token("GITHUB_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def collect_search_7d(days: int = 7, limit: int = 15) -> list[dict]:
    """New AI-topic repos from the last N days, by stars (agents-radar pattern)."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = (f"{API}/search/repositories?q=topic:ai+created:>{since}"
           f"&sort=stars&order=desc&per_page={limit}")
    data = json_get(url, _headers())
    return [make_item("github.search_7d", r["full_name"], r["html_url"],
                      engagement=f"{r['stargazers_count']} stars",
                      published=r.get("created_at", ""),
                      extra=(r.get("description") or "")[:200])
            for r in data.get("items", [])]


def collect_tracked_repos(repos: list[str], limit: int = 5) -> list[dict]:
    """Releases + engaged issues/PRs for each tracked repo."""
    out = []
    for repo in repos:
        rels = json_get(f"{API}/repos/{repo}/releases?per_page={limit}", _headers())
        for rel in rels if isinstance(rels, list) else []:
            out.append(make_item(f"github.releases.{repo}", rel.get("name") or rel.get("tag_name", ""),
                                 rel.get("html_url", ""), engagement="release",
                                 published=rel.get("published_at", "")))
        issues = json_get(
            f"{API}/repos/{repo}/issues?state=open&sort=comments&direction=desc&per_page={limit}",
            _headers())
        for it in issues if isinstance(issues, list) else []:
            if "pull_request" in it:
                continue
            out.append(make_item(f"github.issues.{repo}", it.get("title", ""), it.get("html_url", ""),
                                 engagement=f"{it.get('comments', 0)} comments",
                                 published=it.get("created_at", "")))
    return out


def collect_awesome_lists(repos: list[str]) -> list[dict]:
    """Recent commits on awesome-* lists — new entries surfacing (API diff-watch)."""
    out = []
    for repo in repos:
        commits = json_get(f"{API}/repos/{repo}/commits?per_page=5", _headers())
        for c in commits if isinstance(commits, list) else []:
            out.append(make_item(f"github.awesome.{repo}",
                                 (c.get("commit", {}).get("message") or "")[:150],
                                 c.get("html_url", ""),
                                 published=(c.get("commit", {}).get("author") or {}).get("date", "")))
    return out


def collect_trending() -> list[dict]:
    """github.com/trending HTML scrape (trend-pulse/agents-radar pattern; <=2x/day)."""
    html = http_get("https://github.com/trending")
    out = []
    seen: set[str] = set()
    for m in re.finditer(r'href="/([\w.-]+/[\w.-]+)/stargazers"', html):
        repo = m.group(1)
        if repo in seen or repo.count("/") != 1:
            continue
        seen.add(repo)
        out.append(make_item("github.trending", repo, f"https://github.com/{repo}"))
    return out


def collect_trending_developers() -> list[dict]:
    """github.com/trending/developers HTML scrape (keyless [verified 2026-10-21]).

    Signal: which developers are behind today's hot repos (trend-pulse pattern).
    Rows are <article class="Box-row d-flex" id="pa-<login>">; popular repo
    link inside each article.
    """
    html = http_get("https://github.com/trending/developers")
    arts = re.findall(r'<article class="Box-row d-flex" id="pa-([^"]+)">(.*?)</article>',
                      html, re.S)
    out = []
    for rank, (login, body) in enumerate(arts, 1):
        repo_m = re.search(r'href="/([\w.-]+/[\w.-]+)"', body)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
        repo = repo_m.group(1) if repo_m else ""
        out.append(make_item(
            "github.trending_devs", f"{login}" + (f" · {repo}" if repo else ""),
            f"https://github.com/{login}",
            engagement=f"trending dev rank {rank}" + (f"; popular repo {repo}" if repo else ""),
            extra=(text[:120] if text else "")))
    if not out:
        raise ValueError("github trending/developers: no rows parsed (layout changed?)")
    return out


def collect_quality_gate_probe() -> list[dict]:
    """Group E: OSV keyless POST sanity probe (api.osv.dev [V]).
    Queries one well-known repo; returns [] on success (probe semantics)."""
    urllib_request_json("https://api.osv.dev/v1/query",
                        {"package": {"name": "requests", "ecosystem": "PyPI"}})
    return []


def quality_gate_check(items: list[dict]) -> list[dict]:
    """Group E filter: flag package candidates with OSV advisories (best-effort,
    keyless). GitHub repo links are skipped (OSV indexes packages by
    ecosystem, not by GitHub org/name)."""
    for it in items:
        link = it.get("link", "")
        name = None
        ecosystem = None
        if "pypi.org/project/" in link:
            name = link.split("pypi.org/project/", 1)[1].rstrip("/")
            ecosystem = "PyPI"
        elif "npmjs.com/package/" in link:
            name = link.rsplit("/package/", 1)[-1].rstrip("/")
            ecosystem = "npm"
        if not name:
            continue
        try:
            data = urllib_request_json(
                "https://api.osv.dev/v1/query",
                {"package": {"name": name, "ecosystem": ecosystem}})
            if data.get("vulns"):
                it["extra"] = (it.get("extra", "") + " | OSV advisory present").strip(" |")
                it["gate_rejected"] = True
        except Exception:
            pass  # gate is best-effort; gate failure never blocks an item
    return items


def urllib_request_json(url: str, payload: dict) -> dict:
    import json
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())
