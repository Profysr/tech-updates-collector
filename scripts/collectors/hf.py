"""collectors/hf.py — Hugging Face trending (500 calls/5-min anon [V])."""
from util import json_get, make_item


def collect_trending(limit: int = 15) -> list[dict]:
    data = json_get(f"https://huggingface.co/api/trending?limit={limit}")
    out = []
    entries = data.get("recentlyTrending", data) if isinstance(data, dict) else data
    for e in entries or []:
        repo = e.get("repoData") or e.get("repo") or e
        if isinstance(repo, str):
            rid, kind = repo, "item"
        else:
            rid = repo.get("id") or repo.get("modelId") or ""
            kind = repo.get("pipeline_tag") or repo.get("__typename") or "model"
        if not rid:
            continue
        url = f"https://huggingface.co/{rid}"
        likes = repo.get("likes") if isinstance(repo, dict) else None
        out.append(make_item("hf.trending", rid, url,
                             engagement=f"{likes} likes" if likes else kind))
    return out
