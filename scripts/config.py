"""config.py — minimal YAML-subset loader for sources.yaml (Python stdlib only).

Supports the subset used by our frozen sources.yaml: nested mappings by
indentation, "- item" lists, inline {k: v} dicts, quoted/unquoted scalars,
comments, anchors (&name) and aliases (*name) on list lines, and bare
`key: *alias` / `repos: *watchlist_repos` aliasing. This is deliberately a
small bespoke parser, not a general YAML implementation.
"""
from __future__ import annotations

from pathlib import Path


def _parse_scalar(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_parse_scalar(p) for p in inner.split(",")] if inner else []
    if s.startswith("{") and s.endswith("}"):
        out = {}
        inner = s[1:-1].strip()
        if inner:
            for part in inner.split(","):
                k, _, v = part.partition(":")
                out[k.strip()] = _parse_scalar(v)
        return out
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _strip_comment(line: str) -> str:
    out, in_q = [], None
    for ch in line:
        if in_q:
            out.append(ch)
            if ch == in_q:
                in_q = None
        elif ch in "\"'":
            in_q = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def parse_yaml_subset(text: str) -> dict:
    text = text.lstrip("\ufeff")  # Windows editors prepend a UTF-8 BOM
    lines = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        if stripped.strip().startswith("#"):
            continue
        lines.append(stripped)

    anchors: dict[str, object] = {}

    def parse_block(idx: int, indent: int):
        # Detect whether this block is a list or a mapping.
        first = lines[idx]
        is_list = first.lstrip().startswith("- ")
        if is_list:
            items: list = []
            while idx < len(lines):
                line = lines[idx]
                cur = len(line) - len(line.lstrip())
                if cur < indent or not line.lstrip().startswith("- "):
                    break
                if cur > indent:
                    break
                content = line.lstrip()[2:].strip()
                if content.startswith("&"):  # anchor definition on a list
                    name, _, rest = content.partition(" ")
                    idx += 1
                    sub, idx = parse_block(idx, cur + 2)
                    anchors[name[1:]] = sub
                    items.append(sub)
                    continue
                if content.startswith("*"):  # alias
                    name = content[1:].strip()
                    items.append(anchors.get(name, name))
                    idx += 1
                    continue
                if not content:  # list of blocks
                    idx += 1
                    sub, idx = parse_block(idx, cur + 2)
                    items.append(sub)
                    continue
                if ":" in content and not content.startswith(("{", "[")):
                    # inline single-pair mapping inside a list item
                    k, _, v = content.partition(":")
                    item = {k.strip(): _parse_scalar(v)}
                    idx += 1
                    if idx < len(lines):
                        nxt = lines[idx]
                        ncur = len(nxt) - len(nxt.lstrip())
                        if ncur > cur:
                            sub, idx = parse_block(idx, ncur)
                            if isinstance(sub, dict):
                                item.update(sub)
                    items.append(item)
                    continue
                items.append(_parse_scalar(content))
                idx += 1
            return items, idx

        # mapping
        out: dict = {}
        while idx < len(lines):
            line = lines[idx]
            cur = len(line) - len(line.lstrip())
            if cur < indent:
                break
            if cur > indent:
                idx += 1
                continue
            content = line.strip()
            if ":" not in content:
                idx += 1
                continue
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            idx += 1
            if value.startswith("&"):
                name, _, rest = value.partition(" ")
                sub, idx = parse_block(idx, cur + 2)
                anchors[name[1:]] = sub
                out[key] = sub
                continue
            if value.startswith("*"):
                out[key] = anchors.get(value[1:].strip(), value[1:])
                continue
            if value:
                out[key] = _parse_scalar(value)
            else:
                if idx < len(lines):
                    nxt = lines[idx]
                    ncur = len(nxt) - len(nxt.lstrip())
                    if ncur > cur:
                        sub, idx = parse_block(idx, ncur)
                        out[key] = sub
                    else:
                        out[key] = None
                else:
                    out[key] = None
        return out, idx

    doc, _ = parse_block(0, 0)
    return doc if isinstance(doc, dict) else {}


def load_sources(store_root: Path) -> dict:
    # sources.yaml is code/config: lives beside this package in the project
    # root (knowledge-base/projects/tech-trends/), NOT in the raw store.
    project_root = Path(__file__).resolve().parent.parent
    return parse_yaml_subset((project_root / "sources.yaml").read_text(encoding="utf-8"))


def load_store_config() -> dict:
    """Read scripts/store.config.json (data-root overrides; see paths.py).

    Returns {} when the file is absent (all defaults apply). Malformed
    JSON raises — a typo must not silently reroute the data root.
    """
    cfg_path = Path(__file__).resolve().parent / "store.config.json"
    if not cfg_path.exists():
        return {}
    import json
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return cfg if isinstance(cfg, dict) else {}
