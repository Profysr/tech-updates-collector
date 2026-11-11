"""_lock.py — vendored cross-process advisory lock for the data root.

Vendored (trimmed) from the hub's ``brain/lock.py`` module so the
tech-trends pipeline no longer imports hub code. One lock for the whole
data root: every writer calls ``store_lock()`` with the default name, so
any two writes are serialised. Lock files live under ``<root>/.locks/``
(gitignored, never inside the content tree). The lock is a byte range on
a separate lock file, not on the target — atomic os.replace writes would
not be protected by a lock on the old inode.
"""
from __future__ import annotations

import fcntl  # stdlib, POSIX (this pipeline targets Linux hosts)
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from paths import data_root

__all__ = ["file_lock", "store_lock"]

#: Default seconds to wait before giving up.
DEFAULT_TIMEOUT = 10.0

#: Seconds between attempts when the lock is held.
POLL_INTERVAL = 0.05


def _locks_dir() -> Path:
    # .locks is created lazily inside file_lock; data_root() must already
    # exist by resolver contract.
    return data_root() / ".locks"


@contextmanager
def file_lock(path: Path, timeout: float = DEFAULT_TIMEOUT) -> Iterator[None]:
    """Hold an exclusive flock on *path* for the duration of the block."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"could not acquire lock on {lock_path} within {timeout}s")
                time.sleep(POLL_INTERVAL)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def store_lock(name: str = "store", timeout: float = DEFAULT_TIMEOUT) -> Iterator[None]:
    """Hold the data root's write lock (any two writes are serialised)."""
    with file_lock(_locks_dir() / f"{name}.lock", timeout=timeout):
        yield
