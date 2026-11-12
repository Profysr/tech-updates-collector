"""_lock.py — cross-process advisory lock for the data root.

Backed by the ``filelock`` package (cross-platform; replaces the old
fcntl-based vendored flock polling, so it also works on Windows/macOS).
One lock for the whole data root: every writer calls ``store_lock()``
with the default name, so any two writes are serialised. Lock files live
under ``<root>/.locks/`` (gitignored, never inside the content tree).
The lock is on a separate lock file, not on the target — atomic
os.replace writes would not be protected by a lock on the old inode.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from filelock import FileLock

from paths import data_root

__all__ = ["file_lock", "store_lock"]

#: Default seconds to wait before giving up.
DEFAULT_TIMEOUT = 10.0


def _locks_dir() -> Path:
    # .locks is created lazily inside file_lock; data_root() must already
    # exist by resolver contract.
    return data_root() / ".locks"


@contextmanager
def file_lock(path: Path, timeout: float = DEFAULT_TIMEOUT) -> Iterator[None]:
    """Hold an exclusive lock on *path* for the duration of the block."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path), timeout=timeout)
    with lock:
        yield


@contextmanager
def store_lock(name: str = "store", timeout: float = DEFAULT_TIMEOUT) -> Iterator[None]:
    """Hold the data root's write lock (any two writes are serialised)."""
    with file_lock(_locks_dir() / f"{name}.lock", timeout=timeout):
        yield
