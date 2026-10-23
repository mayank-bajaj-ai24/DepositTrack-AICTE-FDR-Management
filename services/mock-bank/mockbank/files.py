"""Cross-process file safety for the mock bank's state (ledger, signing keys).

`python -m mockbank register` writes the ledger from a separate process while
`python -m mockbank serve` is running, so a thread lock is not enough:

- `locked(path)` holds an inter-process lock file (`<path>.lock`, created with
  O_CREAT | O_EXCL) around every read-modify-write.
- `write_atomic(path, data)` writes a temp file in the same directory and swaps it in with
  `os.replace`, so a reader sees either the old or the new file, never a partial one.

Standard library only, and it works on Windows. A lock file left behind by a crashed process
is treated as stale after `STALE_AFTER` seconds and removed.
"""

import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

LOCK_TIMEOUT = 15.0  # seconds to wait for another writer before giving up
STALE_AFTER = 10.0  # a write takes milliseconds; an older lock file was left by a crash
_POLL = 0.02
_RETRIES = 100  # Windows: replacing or opening a file another process has open fails briefly


class Busy(TimeoutError):
    """Another process held the lock for longer than the timeout."""


def _lock_is_stale(lock: Path) -> bool:
    try:
        return time.time() - lock.stat().st_mtime > STALE_AFTER
    except OSError:  # gone already, or being deleted (Windows)
        return False


@contextmanager
def locked(path: Path, timeout: float | None = None) -> Iterator[None]:
    """Hold the inter-process lock for `path` (threads and processes alike)."""
    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + (LOCK_TIMEOUT if timeout is None else timeout)
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):
            # PermissionError: on Windows the lock file is being deleted by its holder.
            if _lock_is_stale(lock):
                with suppress(FileNotFoundError, PermissionError):
                    lock.unlink()
                continue
            if time.monotonic() > deadline:
                raise Busy(f"{path.name} is locked by another process") from None
            time.sleep(_POLL)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        with suppress(FileNotFoundError):
            lock.unlink()


def _retry_on_windows_sharing(action):
    for attempt in range(_RETRIES):
        try:
            return action()
        except PermissionError:
            if attempt == _RETRIES - 1:
                raise
            time.sleep(_POLL)
    return None  # unreachable


def write_atomic(path: Path, data: bytes) -> None:
    """Replace `path` with `data` in one step; readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _retry_on_windows_sharing(lambda: os.replace(tmp, path))
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def read_bytes(path: Path) -> bytes | None:
    """The file's contents, or None if it does not exist yet."""
    try:
        return _retry_on_windows_sharing(path.read_bytes)
    except FileNotFoundError:
        return None
