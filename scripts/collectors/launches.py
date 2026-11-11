"""collectors/launches.py — Product Hunt (optional token) + YC directory Algolia."""
from util import json_get, make_item, optional_token

YC = "https://ycsearch.startupschool.com/api/v1/companies"
PH_GQL = "https://api.producthunt.com/v2/api/graphql"


def collect_yc(limit: int = 15) -> list[dict]:
    """YC launches via yc-oss/api (unofficial public API mirroring YC's Algolia
    index; daily change summary, keyless). The old ycsearch.startupschool.com
    host no longer resolves."""
    data = json_get("https://yc-oss.github.io/api/changes/latest.json")
    out = []
    for kind in ("added", "updated"):
        for c in (data.get(kind) or []):
            if not isinstance(c, dict):
                continue
            name = c.get("name") or "(unknown)"
            slug = c.get("slug") or ""
            link = (f"https://www.ycombinator.com/companies/{slug}" if slug
                    else c.get("website") or "")
            if not link:
                continue
            out.append(make_item("yc.launches", f"YC {kind}: {name}", link,
                                 engagement=c.get("batch_name", ""),
                                 extra=(c.get("one_liner") or "")[:200]))
    return out[:limit]


def collect_product_hunt(limit: int = 10) -> list[dict]:
    """PH GraphQL via optional free Developer Token (never required).
    Without a token this raises -> caller records 'unknown coverage'."""
    token = optional_token("PRODUCTHUNT_TOKEN")
    if not token:
        raise PermissionError("no PRODUCTHUNT_TOKEN — PH coverage unknown this run")
    query = "{ posts(first: %d, order: VOTES) { edges { node { name tagline url votesCount createdAt } } } }" % limit
    import json
    import urllib.request
    req = urllib.request.Request(
        PH_GQL,
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    out = []
    for edge in data.get("data", {}).get("posts", {}).get("edges", []):
        n = edge.get("node", {})
        out.append(make_item("producthunt.posts", n.get("name", ""), n.get("url", ""),
                             engagement=f"{n.get('votesCount', 0)} votes",
                             extra=n.get("tagline", "")))
    return out
