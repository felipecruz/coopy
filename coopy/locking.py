"""Exclusive writer lock for a data directory (advisory, OS-released on exit)."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import IO

from coopy.error import LockError

LOCK_FILE = "coopy.lock"

# Windows locks a byte past the PID text, so other processes can still read it.
_WINDOWS_LOCK_OFFSET = 4096

# Advisory locks may not conflict within one process on every filesystem, so
# same-process opens are also refused through this registry.
_held: set[str] = set()
_held_guard = threading.Lock()


def _try_lock(file: IO[str]) -> bool:
    if sys.platform == "win32":
        import msvcrt

        file.seek(_WINDOWS_LOCK_OFFSET)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(file: IO[str]) -> None:
    if sys.platform == "win32":
        import msvcrt

        file.seek(_WINDOWS_LOCK_OFFSET)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _holder_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return int(text) if text.isdigit() else None


def _error(directory: Path, pid: int | None) -> LockError:
    holder = f" (held by PID {pid})" if pid is not None else ""
    return LockError(f"Data directory {str(directory)!r} is already open for writing{holder}")


class DirectoryLock:
    """Hold ``coopy.lock`` in ``directory`` until ``release()`` or process exit."""

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory).resolve()
        self.path = self.directory / LOCK_FILE
        self._key = os.path.normcase(str(self.directory))
        self._file: IO[str] | None = None
        with _held_guard:
            if self._key in _held:
                raise _error(self.directory, os.getpid())
            # Never truncate before locking: the holder's PID lives in the file.
            file = open(self.path, "a+", encoding="ascii")
            try:
                if not _try_lock(file):
                    raise _error(self.directory, _holder_pid(self.path))
                file.seek(0)
                file.truncate()
                file.write(str(os.getpid()))
                file.flush()
            except BaseException:
                file.close()
                raise
            self._file = file
            _held.add(self._key)

    def __del__(self) -> None:
        # An unreachable holder releases like a closed file descriptor would.
        if getattr(self, "_file", None) is not None:
            self.release()

    @property
    def held(self) -> bool:
        return self._file is not None

    def release(self) -> None:
        with _held_guard:
            file, self._file = self._file, None
            if file is None:
                return
            _held.discard(self._key)
            try:
                # Leave the file in place: unlinking would race a new holder.
                file.seek(0)
                file.truncate()
                _unlock(file)
            finally:
                file.close()
