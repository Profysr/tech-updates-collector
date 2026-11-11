#!/usr/bin/env python3
"""init_store.py — scaffold the tech-updates data tree at any root.

Friend zero-config flow: creates runs/, runs/sources/, findings/ and the
README/log/watchlist files from scripts/templates/. Refuses to overwrite
existing files unless --force is given.

Usage:
  python scripts/init_store.py [--root <path>] [--force]

Default root: resolved via scripts.paths.data_root() (TECH_UPDATES_ROOT env
-> store.config.json -> <project>/tech-updates).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_TEMPLATES = _SCRIPTS_DIR / "templates"
sys.path.insert(0, str(_SCRIPTS_DIR))

FILES = {
    "README.md": "README.template.md",
    "log.md": "log.md.template",
    "watchlist.md": "watchlist.md.template",
}
DIRS = ["runs", "runs/sources", "findings"]


def existing_targets(root: Path) -> list[Path]:
    """Every target (dirs, files) that already exists at root."""
    hit = []
    for d in DIRS:
        p = root / d
        if p.exists():
            hit.append(p)
    for name in FILES:
        p = root / name
        if p.exists():
            hit.append(p)
    return hit


def init_store(root: Path, force: bool) -> int:
    root.mkdir(parents=True, exist_ok=True)
    if not force:
        existing = existing_targets(root)
        if existing:
            print("Refusing to overwrite existing files/dirs at", root)
            for p in existing:
                print("  exists:", p)
            print("Re-run with --force to overwrite.")
            return 1
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    for name, template in FILES.items():
        src = _TEMPLATES / template
        if not src.is_file():
            print(f"Missing template: {src}", file=sys.stderr)
            return 2
        shutil.copyfile(src, root / name)
    print(f"Initialized tech-updates store at {root}:")
    for line in tree_lines(root):
        print("  " + line)
    return 0


def tree_lines(root: Path) -> list[str]:
    """Sorted listing of the created tree (dirs first)."""
    lines = [root.name + "/"]
    dirs = sorted(p for p in root.rglob("*") if p.is_dir())
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for p in dirs + files:
        depth = len(p.relative_to(root).parts)
        lines.append("  " * depth + p.name + ("/" if p.is_dir() else ""))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=None,
                    help="data root (default: resolved from paths.py)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing files/dirs")
    args = ap.parse_args()
    try:
        root = args.root.resolve() if args.root else paths_data_root()
    except Exception as e:
        print(f"Cannot resolve data root: {e}", file=sys.stderr)
        return 2
    return init_store(root, args.force)


def paths_data_root() -> Path:
    """Delegate to scripts.paths.data_root(); keeps sys.path local."""
    import paths  # noqa: E402  (scripts dir injected above)
    return paths.data_root()


if __name__ == "__main__":
    sys.exit(main())
