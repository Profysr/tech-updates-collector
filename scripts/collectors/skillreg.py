"""collectors/skillreg.py — officialskills.sh (Group A snapshot-diff) and
www.skills.sh (Group D adoption-velocity leaderboard). Both keyless HTML
scrapes; access verified 2026-10-21 (see sources.yaml amendment note).

officialskills.sh: homepage exposes a "Last Updated" stat and the full
official skill list as hrefs to /<org>/skills/<name> (660 skills / 56 dev
teams at probe time). Snapshot-diff pattern (agents-radar / snapshot_diff):
each run stores the sorted skill path list under state/snapshots/ and emits
items only for skills added since the previous run (first run = baseline
snapshot item).

www.skills.sh: leaderboard rows on / (all-time), /trending (24h) and /hot.
Each row: rank, skill name, owner/repo, install count (all-time/trending)
or count + delta (hot). Install counts are diffed for every tracked skill;
new entries = new skills surfacing.
"""
import re
from pathlib import Path

from bs4 import BeautifulSoup

from util import http_get, make_item

OFFICIAL_URL = "https://officialskills.sh"
SKILLSH_URL = "https://www.skills.sh"

SNAPDIR = Path(__file__).resolve().parents[2] / "state" / "snapshots"


def _read_snap(name: str) -> dict[str, str]:
    p = SNAPDIR / name
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "\t" in line:
            k, _, v = line.partition("\t")
            out[k] = v
    return out


def _write_snap(name: str, data: dict[str, str]) -> None:
    SNAPDIR.mkdir(parents=True, exist_ok=True)
    (SNAPDIR / name).write_text(
        "# officialskills.sh skill-path snapshot (one path<TAB>meta per line)\n"
        + "".join(f"{k}\t{v}\n" for k, v in sorted(data.items())),
        encoding="utf-8")


def collect_officialskills() -> list[dict]:
    """Group A: official agent-skill registry, snapshot-diff (keyless [V])."""
    html = http_get(OFFICIAL_URL)
    soup = BeautifulSoup(html, "html.parser")
    _SKILL_HREF = re.compile(r"^/[A-Za-z0-9_.\-]+/skills/[A-Za-z0-9_.\-]+$")
    paths = sorted({a.get("href") for a in soup.select("a[href]")
                    if _SKILL_HREF.match(a.get("href") or "")})
    if not paths:
        raise ValueError("officialskills.sh: no skill hrefs parsed (layout changed?)")
    last_updated = ""
    label = soup.find("span", string=re.compile(r"Last Updated"))
    if label:
        nxt = label.find_next("span")
        if nxt:
            last_updated = nxt.get_text(strip=True)

    prev = _read_snap("officialskills.txt")
    new = [p for p in paths if p not in prev]
    _write_snap("officialskills.txt", {p: last_updated for p in paths})

    out = []
    if not prev:  # first run: baseline snapshot item, no fake "new" flood
        out.append(make_item(
            "officialskills.snapshot",
            f"officialskills.sh baseline: {len(paths)} official skills"
            f"{f', last updated {last_updated}' if last_updated else ''}",
            OFFICIAL_URL,
            engagement=f"{len(paths)} skills"))
    else:
        for p in new[:30]:
            out.append(make_item(
                "officialskills.new", p.strip("/"),
                f"{OFFICIAL_URL}{p}",
                engagement="new official skill"
                           + (f"; registry updated {last_updated}" if last_updated else "")))
    return out


def _parse_skillsh_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select('a[href*="/skills/"]'):
        href = a.get("href") or ""
        if not href.startswith("/") or href.count("/") < 3:
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        parts = text.split()
        if len(parts) < 3:
            continue
        rank, name = parts[0], parts[1]
        delta = None
        if parts[-1].startswith("+"):
            delta = parts[-1]
            parts = parts[:-1]
        owner_repo = "/".join(href.strip("/").split("/")[:-2])
        out.append({"path": href, "name": name, "owner_repo": owner_repo,
                    "rank": rank, "count": parts[-1], "delta": delta})
    return out


def collect_skillsh(top_n: int = 20) -> list[dict]:
    """Group D: skills.sh install-count leaderboard, diff vs snapshot.

    Emits: watchlist/all tracked skills whose install count changed since
    the previous run, plus new entries; first run records a baseline.
    """
    html = http_get(SKILLSH_URL + "/")
    rows = _parse_skillsh_rows(html)
    if not rows:
        raise ValueError("skills.sh: no leaderboard rows parsed (layout changed?)")

    prev = _read_snap("skillsh_installs.txt")
    cur = {r["path"]: r["count"] for r in rows}
    _write_snap("skillsh_installs.txt", cur)

    out = []
    if not prev:
        for r in rows[:top_n]:
            out.append(make_item(
                "skillsh.installs", f"{r['owner_repo']} · {r['name']}",
                SKILLSH_URL + r["path"],
                engagement=f"all-time installs {r['count']} (rank {r['rank']})",
                extra="baseline snapshot"))
    else:
        changed = [(p, prev[p], c) for p, c in cur.items()
                   if p in prev and prev[p] != c]
        added = [p for p in cur if p not in prev]
        for p, old, new in changed[:top_n]:
            out.append(make_item(
                "skillsh.installs", f"install-count change: {p.strip('/')}",
                SKILLSH_URL + p,
                engagement=f"installs {old} -> {new}"))
        for p in added[:top_n]:
            r = next(x for x in rows if x["path"] == p)
            out.append(make_item(
                "skillsh.new", f"new skill entry: {r['owner_repo']} · {r['name']}",
                SKILLSH_URL + p,
                engagement=f"installs {r['count']} (rank {r['rank']})"))
    return out


def collect_skillsh_trending(limit: int = 15) -> list[dict]:
    """Group D: skills.sh /trending (24h) + /hot tabs — what is moving now."""
    out = []
    for tab, key in (("trending", "skillsh.trending"), ("hot", "skillsh.hot")):
        html = http_get(f"{SKILLSH_URL}/{tab}")
        for r in _parse_skillsh_rows(html)[:limit]:
            eng = f"installs {r['count']}"
            if r["delta"]:
                eng += f" ({r['delta']} in 24h)"
            out.append(make_item(f"{key}", f"{r['owner_repo']} · {r['name']}",
                                 SKILLSH_URL + r["path"],
                                 engagement=eng, extra=f"rank {r['rank']}"))
    return out
