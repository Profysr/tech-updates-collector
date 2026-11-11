"""_io.py — vendored UTF-8-safe file IO with atomic writes.

Vendored (trimmed) from the hub's ``brain/textio.py`` module so the
tech-trends pipeline no longer imports hub code. Same semantics the hub
AGENTS.md demands: writes are atomic (tmp + fsync + os.replace), reads are
tolerant (undecodable bytes become U+FFFD, BOM stripped), line endings
always LF.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Union

ENCODING = "utf-8"
NEWLINE = "\n"

PathLike = Union[str, "os.PathLike[str]", Path]


def read_text(path: PathLike) -> str:
    """Read a file as UTF-8, replacing undecodable bytes; strip a UTF-8 BOM."""
    data = Path(path).read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode(ENCODING, errors="replace")


def write_text(path: PathLike, text: str) -> None:
    """Atomically write *text* as UTF-8 with LF newlines.

    tmp sibling -> flush -> fsync -> os.replace, so a process killed
    mid-write cannot leave a truncated target.
    """
    target = Path(path)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=target.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=ENCODING, newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
