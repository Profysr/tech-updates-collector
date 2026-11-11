"""collectors/arxiv.py — arXiv API query (keyless, announce cycle)."""
import re
from util import http_get, make_item

BASE = "http://export.arxiv.org/api/query"


def collect(categories: list[str] | None = None, limit: int = 10) -> list[dict]:
    cats = "+OR+".join(f"cat:{c}" for c in (categories or ["cs.AI"]))
    xml = http_get(f"{BASE}?search_query={cats}&sortBy=submittedDate&sortOrder=descending&max_results={limit}")
    out = []
    for m in re.finditer(r"<entry>(.*?)</entry>", xml, re.S):
        block = m.group(1)
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else "(untitled)"
        link_m = re.search(r"<id>(.*?)</id>", block)
        pub = re.search(r"<published>(.*?)</published>", block)
        out.append(make_item("arxiv.cs", title, link_m.group(1).strip() if link_m else "",
                             published=pub.group(1) if pub else ""))
    return out
