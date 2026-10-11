"""Delete checkpoints and journals that recovery of the current state never reads."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from coopy import fileutils
from coopy.error import ConfigurationError
from coopy.locking import DirectoryLock

PathLike = str | os.PathLike[str]


@dataclass(frozen=True)
class PruneReport:
    """File names removed by a prune, oldest first, and the checkpoints kept."""

    snapshots: list[str] = field(default_factory=list)
    journals: list[str] = field(default_factory=list)
    kept_snapshots: list[str] = field(default_factory=list)

    @property
    def removed(self) -> list[str]:
        return self.snapshots + self.journals


def validate_prune(keep: int, keep_for: timedelta | None) -> None:
    if type(keep) is not int or keep < 1:
        raise ConfigurationError("keep must be an integer of at least 1")
    if keep_for is not None and (not isinstance(keep_for, timedelta) or keep_for < timedelta(0)):
        raise ConfigurationError("keep_for must be a nonnegative timedelta or None")


def prune_files(basedir: PathLike, *, keep: int, keep_for: timedelta | None = None) -> PruneReport:
    """Prune ``basedir``; the caller holds its directory lock and domain lock.

    Keeps the newest ``keep`` checkpoints plus any published within
    ``keep_for``, and every journal numbered at or after the oldest kept
    checkpoint. Recovery reads only the newest checkpoint and the journals
    after it, so neither is ever removed, and only files listed here are.
    """
    validate_prune(keep, keep_for)
    directory = Path(basedir)
    snapshots = fileutils.list_snapshot_files(directory) or []
    if len(snapshots) <= keep:
        return PruneReport(kept_snapshots=snapshots)
    candidates = snapshots[:-keep]
    if keep_for is not None:
        cutoff = time.time() - keep_for.total_seconds()
        # Keep everything from the first candidate that is still recent enough.
        for index, name in enumerate(candidates):
            if (directory / name).stat().st_mtime >= cutoff:
                candidates = candidates[:index]
                break
    kept = snapshots[len(candidates) :]
    if not candidates:
        return PruneReport(kept_snapshots=kept)
    oldest_kept = fileutils.get_number(kept[0])
    journals = [
        name
        for name in fileutils.list_log_files(directory) or []
        if fileutils.get_number(name) < oldest_kept
    ]
    # Oldest first: an interruption leaves a shorter but still contiguous history.
    for name in sorted(candidates + journals, key=fileutils.get_number):
        (directory / name).unlink(missing_ok=True)
    fileutils.sync_directory(directory)
    return PruneReport(snapshots=candidates, journals=journals, kept_snapshots=kept)


def prune(basedir: PathLike, *, keep: int, keep_for: timedelta | None = None) -> PruneReport:
    """Prune a closed data directory while holding its writer lock.

    Use ``coopy.control(system).prune(...)`` for a directory that is open.
    Raises ``LockError`` when another writer holds the directory.
    """
    validate_prune(keep, keep_for)
    directory = Path(basedir)
    if not directory.is_dir():
        raise ConfigurationError(f"{str(directory)!r} is not a data directory")
    lock = DirectoryLock(directory)
    try:
        return prune_files(directory, keep=keep, keep_for=keep_for)
    finally:
        lock.release()
