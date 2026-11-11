#!/usr/bin/env python3
"""collect.py — one collection run: sources.yaml -> collectors -> store.

Usage:
    python collect.py               # full run (all groups, keyed from sources.yaml)
    python collect.py --probe       # per-collector live check, no store writes
    python collect.py --list-sources # catalog for setup.py: key|plate|token rows

Rules: pyyaml only (requirements.txt); store resolved relative to script;
tokens optional via env or keyring/.env (setup.py stores via keyring);
failed source logs "unknown coverage", never "no news"; watermarks advance
only on success.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import util
from collectors import (adoption, arxiv, chatter, github, hf, launches,
                        marketplace, skillreg, trendshift)

DEFAULT_AWESOME = ["anthropics/skills", "wshobson/agents", "hesreallyhim/awesome-claude-code"]

# Catalog for setup.py --list-sources: (runner key, plate entry, token env).
# Adding a source = add its runner AND one row here; setup picks up new keys automatically.
CATALOG = [
    ("hn.front_page", "launches.hn_algolia", "keyless"),
    ("hn.show_hn", "launches.hn_algolia", "keyless"),
    ("github.search_7d", "code.github_search_7d", "GITHUB_TOKEN"),
    ("github.tracked_repos", "code.tracked_repos", "GITHUB_TOKEN"),
    ("github.awesome_lists", "catalogs.awesome_lists", "GITHUB_TOKEN"),
    ("github.trending", "code.github_trending", "keyless"),
    ("github.trending_devs", "code.github_trending_developers", "keyless"),
    ("hf.trending", "adoption.hf_trending", "keyless"),
    ("arxiv.cs", "launches.arxiv", "keyless"),
    ("pypi.rss", "adoption.pypi", "keyless"),
    ("npm.downloads", "adoption.npm_downloads", "keyless"),
    ("yc.launches", "launches.yc_launches", "keyless"),
    ("producthunt.posts", "launches.product_hunt", "PRODUCTHUNT_TOKEN"),
    ("vscode.marketplace", "catalogs.vscode_marketplace", "keyless"),
    ("openvsx", "catalogs.openvsx", "keyless"),
    ("reddit.rss", "chatter.reddit_rss", "keyless"),
    ("vendor.rss", "chatter.vendor_rss", "keyless"),
    ("chatter.other", "chatter.devto+lobsters", "keyless"),
    ("officialskills.snapshot", "catalogs.officialskills", "keyless"),
    ("skillsh.installs", "adoption.skillssh", "keyless"),
    ("skillsh.trending_hot", "adoption.skillssh", "keyless"),
    ("trendshift.repos", "code.trendshift", "keyless"),
    ("quality_gate.osv", "quality_gate.security", "keyless"),
]


def main(argv: list[str]) -> int:
    if "--list-sources" in argv:  # before any config/root reads: works on a bare clone
        for key, plate, token in CATALOG:
            print(f"{key}|{plate}|{token}")
        return 0

    probe_only = "--probe" in argv
    # Data root: TECH_UPDATES_ROOT env -> store.config.json -> <project>/tech-updates.
    root = util.store_root()  # delegates to paths.data_root()
    try:
        sources = config.load_sources(root)
    except config.ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    wl = sources.get("watchlist", {}) or {}
    repos = list(wl.get("repos") or [])
    packages = list(wl.get("packages") or [])
    launches_cfg = sources.get("launches", {}) or {}
    arxiv_cfg = (launches_cfg.get("arxiv", {}) or {}).get("categories")
    arxiv_cat_list = [str(c) for c in arxiv_cfg if c] if isinstance(arxiv_cfg, list) else ["cs.AI"]

    jobs: list[tuple[str, object]] = [
        ("hn.front_page", lambda: hn_front()),
        ("hn.show_hn", lambda: hn_show()),
        ("github.search_7d", github.collect_search_7d),
        ("github.tracked_repos", lambda: github.collect_tracked_repos(repos)),
        ("github.awesome_lists", lambda: github.collect_awesome_lists(DEFAULT_AWESOME)),
        ("github.trending", github.collect_trending),
        ("github.trending_devs", github.collect_trending_developers),
        ("hf.trending", hf.collect_trending),
        ("arxiv.cs", lambda: arxiv.collect(arxiv_cat_list)),
        ("pypi.rss", adoption.collect_pypi),
        ("npm.downloads", lambda: adoption.collect_npm(packages)),
        ("yc.launches", launches.collect_yc),
        ("producthunt.posts", launches.collect_product_hunt),
        ("vscode.marketplace", marketplace.collect_vscode),
        ("openvsx", marketplace.collect_openvsx),
        ("reddit.rss", chatter.collect_reddit),
        ("vendor.rss", chatter.collect_vendors),
        ("chatter.other", chatter.collect_other),
        ("officialskills.snapshot", skillreg.collect_officialskills),
        ("skillsh.installs", skillreg.collect_skillsh),
        ("skillsh.trending_hot", skillreg.collect_skillsh_trending),
        ("trendshift.repos", trendshift.collect),
        ("quality_gate.osv", github.collect_quality_gate_probe),
        ]
    # run.disable (written by setup.py's picker) skips sources before they run.
    disabled = set((sources.get("run") or {}).get("disable") or [])
    jobs = [(k, fn) for k, fn in jobs if k not in disabled]
    if disabled:
        print(f"disabled: {', '.join(sorted(disabled))}")
    if not jobs:
        print("All sources disabled in run.disable — nothing to do.")
        return 0
    results = [util.run_collector(fn, key) for key, fn in jobs]

    coverage = [r.coverage_line() for r in results]
    for line in coverage:
        print(line)

    if probe_only:
        # All-fail = broken config/network, not a quiet "everything fine".
        return 0 if any(r.ok for r in results) else 1

    import store  # deferred: pulls sqlite3; probe must run anywhere

    cursors = store.read_cursors()
    new_items: list[dict] = []
    seen_updates: dict[str, str] = {}
    watermarks: dict[str, str] = {}
    for res in results:
        if not res.ok:
            continue  # failed source: no watermark advance (unknown coverage)
        fresh = store.filter_new(res.items, cursors, res.source_key)
        new_items += fresh
        for it in fresh:
            seen_updates[store.seen_key(cursors, res.source_key, it)] = it["fetched_at"]
        watermarks[store.watermark_key(res.source_key)] = util.now_utc()

    inbox_path = store.write_inbox(new_items, coverage)
    n = store.write_sources(new_items)
    if results and all(r.ok for r in results):
        store.write_cursors({**seen_updates, **watermarks})  # advance only on full success
    elif seen_updates:
        ok_keys = {k for r in results if r.ok for k in [store.seen_key(cursors, r.source_key, it) for it in r.items]}
        store.write_cursors({k: v for k, v in seen_updates.items() if k in ok_keys})
        store.write_cursors({store.watermark_key(r.source_key): util.now_utc() for r in results if r.ok})
    store.append_log(coverage, inbox_path, len(new_items))
    print(f"\nRun complete: {len(new_items)} new items -> {inbox_path.name}; {n} recorded in sources/.")
    return 0


def hn_front():
    from collectors import hn
    return hn.collect_front_page()


def hn_show():
    from collectors import hn
    return hn.collect_show_hn()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
