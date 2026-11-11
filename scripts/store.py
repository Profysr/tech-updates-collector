"""store.py — cursors (watermarks/seen-IDs), dedupe, inbox + sources writers.

Store layout per tech-trends/README.md:
  runs/<date>-<time>.md          raw capture, one file per run, never edited after
  runs/sources/YYYY-MM-DD/<src>.md  deduped survivors with provenance
  state/cursors.txt               key=value watermarks + seen item ids (git-diffable)
  log.md                          run notes
Watermarks advance only on success (errata §4.3).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import _lock
import _textio as textio
import paths
from util import item_key  # noqa: F401
from util import store_root  # noqa: F401  (re-exported for collect.py)

CURSORS = "state/cursors.txt"


def cursors_path() -> Path:
    """Cursors are DURABLE pipeline state (seen-IDs prevent duplicate
    collection), so they live with the project code, not the data root:
    <project>/state/cursors.txt"""
    return paths.cursors_path()


def read_cursors() -> dict[str, str]:
    cur = {}
    p = cursors_path()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cur[k.strip()] = v.strip()
    return cur


def write_cursors(update: dict[str, str]) -> None:
    """Merge *update* into the durable cursors file.

    Read-merge-write, so it takes the hub lock. Without it, two collectors
    running at once both read the cursors, both merged, both wrote -- and
    the second write dropped the first one's watermark and seen-id
    updates. A dropped seen-id means the same items get collected again.
    """
    with _lock.store_lock():
        cur = read_cursors()
        cur.update({k: v for k, v in update.items() if v is not None})
        lines = ["# tech-trends watermarks / seen ids (key=value; advanced only on success)"]
        for k in sorted(cur):
            lines.append(f"{k}={cur[k]}")
        textio.write_text(cursors_path(), "\n".join(lines) + "\n")  # type: ignore[attr-defined]  (vendored scripts/_io.py, not stdlib _io)


def seen_key(cursors: dict, source_key: str, item: dict) -> str:
    return f"seen.{source_key}.{item_key(item)}"


def filter_new(items: list[dict], cursors: dict, source_key: str) -> list[dict]:
    """Dedupe vs cursors: drop items whose seen-key is already recorded."""
    out = []
    for it in items:
        if seen_key(cursors, source_key, it) not in cursors:
            out.append(it)
    return out


def record_seen(source_key: str, items: list[dict]) -> dict[str, str]:
    return {seen_key(read_cursors(), source_key, it): it["fetched_at"] for it in items}


def watermark_key(source_key: str) -> str:
    return f"wm.{source_key}"


def run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_inbox(items: list[dict], coverage_lines: list[str]) -> Path:
    """Raw capture, one file per run. Machine-written; never edited after."""
    root = store_root()
    inbox = root / "runs"
    inbox.mkdir(parents=True, exist_ok=True)
    with _lock.store_lock():
        # The stamp is minute-resolution: two runs in the same minute used
        # to land on the same filename, and the second write replaced the
        # first run's capture. A run file is never overwritten.
        path = inbox / f"{run_stamp()}.md"
        n = 1
        while path.exists():
            path = inbox / f"{run_stamp()}-{n}.md"
            n += 1
        lines = [
            f"# Inbox run {run_stamp()} (UTC)",
            "",
            "## Coverage",
            "",
        ]
        lines += [f"- {c}" for c in coverage_lines]
        lines += ["", f"## Items ({len(items)})", ""]
        if not items:
            lines.append("(no new items this run — collectors with errors above mean unknown coverage)")
        for it in items:
            eng = f" · engagement: {it['engagement']}" if it.get("engagement") else ""
            pub = f" · published: {it['published']}" if it.get("published") else ""
            lines.append(f"- [{it['title']}]({it['link']}) — source: {it['source']}{eng}{pub}")
            if it.get("extra"):
                lines.append(f"  - {it['extra']}")
        lines.append("")
        textio.write_text(path, "\n".join(lines))  # type: ignore[attr-defined]  (vendored scripts/_io.py, not stdlib _io)
    return path


def write_sources(items: list[dict]) -> int:
    """Deduped survivors -> sources/YYYY-MM-DD/, provenance lines, append-only."""
    if not items:
        return 0
    day_dir = store_root() / "runs" / "sources" / today()
    day_dir.mkdir(parents=True, exist_ok=True)
    by_source: dict[str, list[dict]] = {}
    for it in items:
        by_source.setdefault(it["source"], []).append(it)
    n = 0
    # The lock covers the exists-then-open race: two runs could both see
    # no file, both open it "w", and the second truncated the first's
    # entries.
    with _lock.store_lock():
        for source, its in sorted(by_source.items()):
            path = day_dir / f"{re.sub(r'[^a-z0-9_.-]+', '_', source.lower())}.md"
            mode = "a" if path.exists() else "w"
            with path.open(mode, encoding="utf-8") as f:
                if mode == "a":
                    f.write(f"\n\n## appended {run_stamp()}\n\n")
                else:
                    f.write(f"# {source} — first seen {today()}\n\n")
                for it in its:
                    eng = f" | engagement: {it['engagement']}" if it.get("engagement") else ""
                    f.write(
                        f"- {it['title']} | link: {it['link']} | source: {it['source']}"
                        f"{eng} | published: {it['published']} | first-seen: {it['fetched_at']}\n"
                    )
                    n += 1
    return n


def append_log(coverage_lines: list[str], inbox_path: Path, new_count: int) -> None:
    # Run notes: <root>/log.md (append; header if the file is new).
    log = paths.log_path()
    with _lock.store_lock():
        if not log.exists():
            with log.open("w", encoding="utf-8") as f:
                f.write("# Tech-trends run log\n\nAppend-only; one `## Run` block per collection run (UTC).\n")
        with log.open("a", encoding="utf-8") as f:
            f.write(f"\n## Run {run_stamp()} UTC\n")
            f.write(f"- run: {inbox_path.name} ({new_count} new items)\n")
            for line in coverage_lines:
                f.write(f"- {line}\n")
