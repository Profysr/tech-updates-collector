"""collectors/github.py — GitHub REST + Trending scrape + anthropics/skills.

60 req/hr unauth; optional GITHUB_TOKEN lifts to 5,000/hr [verified].
"""
from bs4 import BeautifulSoup

import github as gh_module
from github import Github

from util import USER_AGENT, http_get, make_item, optional_token, post_json

PER_PAGE_DEFAULT = 30


def _client() -> Github:
    """PyGithub client; optional_token("GITHUB_TOKEN") lifts rate limits.

    Keyless works (60 req/hr); a token only raises the ceiling. Paginated
    lists are lazy — they fetch more pages on demand and count against
    the same rate limit.
    """
    tok = optional_token("GITHUB_TOKEN")
    if tok:
        auth = gh_module.Auth.Token(tok)
    else:
        auth = None
    return Github(auth=auth, per_page=PER_PAGE_DEFAULT, user_agent=USER_AGENT)


def collect_search_7d(days: int = 7, limit: int = 15) -> list[dict]:
    """New AI-topic repos from the last N days, by stars (agents-radar pattern)."""
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    gh = _client()
    results = gh.search_repositories(
        query=f"topic:ai created:>{since}", sort="stars", order="desc")
    out = []
    for r in results[:limit]:
        out.append(make_item("github.search_7d", r.full_name, r.html_url,
                             engagement=f"{r.stargazers_count} stars",
                             published=r.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                                       if r.created_at else "",
                             extra=(r.description or "")[:200]))
    return out


def collect_tracked_repos(repos: list[str], limit: int = 5) -> list[dict]:
    """Releases + engaged issues/PRs for each tracked repo."""
    out = []
    gh = _client()
    for repo in repos:
        gh_repo = gh.get_repo(repo)
        for rel in gh_repo.get_releases()[:limit]:
            out.append(make_item(
                f"github.releases.{repo}",
                rel.title or rel.tag_name or "",
                rel.html_url or "",
                engagement="release",
                published=rel.published_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                          if rel.published_at else ""))
        for it in gh_repo.get_issues(
                state="open", sort="comments", direction="desc")[:limit]:
            if it.pull_request is not None:
                continue
            out.append(make_item(f"github.issues.{repo}", it.title, it.html_url,
                                 engagement=f"{it.comments} comments",
                                 published=it.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                                           if it.created_at else ""))
    return out


def collect_awesome_lists(repos: list[str]) -> list[dict]:
    """Recent commits on awesome-* lists — new entries surfacing (API diff-watch)."""
    out = []
    gh = _client()
    for repo in repos:
        for c in gh.get_repo(repo).get_commits()[:5]:
            msg = c.commit.message or ""
            author = c.commit.author
            out.append(make_item(f"github.awesome.{repo}",
                                 msg[:150],
                                 c.html_url or "",
                                 published=author.date.strftime("%Y-%m-%dT%H:%M:%SZ")
                                           if author and author.date else ""))
    return out


def collect_trending() -> list[dict]:
    """github.com/trending HTML scrape (trend-pulse/agents-radar pattern; <=2x/day)."""
    html = http_get("https://github.com/trending")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen: set[str] = set()
    for a in soup.select('a[href$="/stargazers"]'):
        href = a.get("href") or ""
        repo = href.lstrip("/").removesuffix("/stargazers")
        if not repo or repo in seen or repo.count("/") != 1:
            continue
        seen.add(repo)
        out.append(make_item("github.trending", repo, f"https://github.com/{repo}"))
    if not out:
        raise ValueError("github trending: no rows parsed (layout changed?)")
    return out


def collect_trending_developers() -> list[dict]:
    """github.com/trending/developers HTML scrape (keyless [verified 2026-10-21]).

    Signal: which developers are behind today's hot repos (trend-pulse pattern).
    Rows are <article class="Box-row d-flex" id="pa-<login>">; popular repo
    link inside each article.
    """
    html = http_get("https://github.com/trending/developers")
    soup = BeautifulSoup(html, "html.parser")
    arts = [a for a in soup.select("article.Box-row[id^=pa-]")]
    out = []
    for rank, art in enumerate(arts, 1):
        login = (art.get("id") or "")[3:]  # strip "pa-" prefix
        repo = ""
        for a in art.select("a[href]"):
            href = a.get("href") or ""
            parts = href.strip("/").split("/")
            if len(parts) == 2 and all(parts) and parts[0] not in ("features", "topics", "trending"):
                repo = "/".join(parts)
                break
        text = art.get_text(" ", strip=True)
        text = " ".join(text.split())
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
    post_json("https://api.osv.dev/v1/query",
              {"package": {"name": "requests", "ecosystem": "PyPI"}})
    return []
