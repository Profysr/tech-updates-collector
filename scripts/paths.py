"""paths.py — data-root resolver for the tech-trends pipeline.

Decouples the collector from the shared-memory hub tree. All RAW + curated
output goes under ONE configurable data root; only durable pipeline state
(cursors) and code stay in the project folder.

Precedence (first match wins):
  1. ``TECH_UPDATES_ROOT`` env var — must point at an existing directory
     (we refuse to invent a path the operator mistyped).
  2. ``tech_updates_root`` in ``scripts/store.config.json`` — must exist.
  3. Default: ``<project>/tech-updates`` (friend zero-config; the project
     folder is the code folder, so a fresh clone is self-contained).

Target layout (later phases populate it via init_store.py):
  <root>/runs/           raw capture, one file per run
  <root>/runs/sources/   deduped survivors with provenance
  <root>/findings/       curated output
  <root>/log.md          run log
  <root>/watchlist.md    curated watchlist
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_CODE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = Path(__file__).resolve().parent / "store.config.json"


def project_dir() -> Path:
    """The code folder (this package's parent): sources.yaml, state/, plans/."""
    return _CODE_DIR


def data_root() -> Path:
    """Resolve the data root per the documented precedence."""
    env = os.environ.get("TECH_UPDATES_ROOT", "").strip()
    if env:
        p = Path(env).expanduser()
        if not p.is_dir():
            raise FileNotFoundError(
                f"TECH_UPDATES_ROOT={env} does not exist — create it first")
        return p.resolve()
    if _CONFIG_PATH.exists():
        try:
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"{_CONFIG_PATH.name} is unreadable: {e}") from e
        val = str(cfg.get("tech_updates_root") or "").strip()
        if val:
            p = Path(val).expanduser()
            if not p.is_dir():
                raise FileNotFoundError(
                    f"store.config.json tech_updates_root={val} does not exist")
            return p.resolve()
    return _CODE_DIR / "tech-updates"


def runs_dir() -> Path:
    return data_root() / "runs"


def sources_dir() -> Path:
    return runs_dir() / "sources"


def findings_dir() -> Path:
    return data_root() / "findings"


def watchlist_path() -> Path:
    return data_root() / "watchlist.md"


def log_path() -> Path:
    return data_root() / "log.md"


def cursors_path() -> Path:
    """Durable pipeline state stays with the code, NOT in the data root."""
    return _CODE_DIR / "state" / "cursors.txt"
