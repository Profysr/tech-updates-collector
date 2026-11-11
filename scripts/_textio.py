"""_textio.py — UTF-8-safe file IO with atomic writes.

Backed by the ``atomicwrites`` package (tmp sibling + os.replace; replaces
the hand-rolled vendored version). Same semantics the hub AGENTS.md
demands: writes are atomic (a crash mid-write cannot leave a truncated
target), reads are tolerant (undecodable bytes become U+FFFD, BOM
stripped), line endings always LF.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

from atomicwrites import atomic_write

ENCODING = "utf-8"
NEWLINE = "\n"

PathLike = Union[str, "os.PathLike[str]", Path]

__all__ = ["ENCODING", "NEWLINE", "PathLike", "read_text", "write_text"]


def read_text(path: PathLike) -> str:
    """Read a file as UTF-8, replacing undecodable bytes; strip a UTF-8 BOM."""
    data = Path(path).read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode(ENCODING, errors="replace")


def write_text(path: PathLike, text: str) -> None:
    """Atomically write *text* as UTF-8 with LF newlines.

    atomic_write stages a tmp sibling then os.replace, so a process
    killed mid-write cannot leave a truncated target.
    """
    target = Path(path)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    with atomic_write(target, overwrite=True, encoding=ENCODING, newline=NEWLINE) as f:
        f.write(text)
