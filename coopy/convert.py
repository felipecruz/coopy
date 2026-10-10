"""Copy a data directory into a new one with another serializer or signing key."""

from __future__ import annotations

import enum
import os
import shutil
from pathlib import Path
from typing import Any

from coopy import fileutils, manifest
from coopy.compression import validate_compression
from coopy.error import ConfigurationError
from coopy.foundation import RecordClock
from coopy.integrity import Integrity, validate_secret
from coopy.locking import DirectoryLock
from coopy.restore import RecoveryReport, recover
from coopy.serialization import ActionSchemas, Serializer, StateSchemas
from coopy.snapshot import SnapshotManager
from coopy.utils import inject

PathLike = str | os.PathLike[str]


class _Unchanged(enum.Enum):
    UNCHANGED = "unchanged"


UNCHANGED = _Unchanged.UNCHANGED


class _Recovering:
    """Placeholder root: recovery replaces it with the checkpoint's object."""


def _first_missing(path: Path) -> Path | None:
    """The outermost ancestor of ``path`` (or itself) that does not exist yet."""
    missing = None
    for candidate in (path, *path.parents):
        if candidate.exists():
            break
        missing = candidate
    return missing


def _empty_destination(dst: Path) -> bool:
    """True when ``dst`` exists already; refuse anything but an empty directory."""
    if not dst.exists():
        return False
    if not dst.is_dir():
        raise ConfigurationError(f"Destination {str(dst)!r} is not a directory")
    if any(dst.iterdir()):
        raise ConfigurationError(f"Destination {str(dst)!r} is not empty")
    return True


def convert(
    src: PathLike,
    dst: PathLike,
    *,
    serializer: Serializer | None = None,
    secret: bytes | None = None,
    new_serializer: Serializer | None | _Unchanged = UNCHANGED,
    new_secret: bytes | None | _Unchanged = UNCHANGED,
    snapshot_compression: str | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
) -> RecoveryReport:
    """Recover ``src`` strictly and write its state as one checkpoint in ``dst``.

    ``serializer`` and ``secret`` open ``src`` exactly as ``coopy.open`` would.
    ``new_serializer`` and ``new_secret`` configure ``dst`` and default to the
    source settings; pass ``new_secret=None`` to write unsigned storage. ``dst``
    must be missing or an empty directory. ``src`` storage files are never
    written; its writer lock is held while reading. On any failure everything
    created for ``dst`` is removed. Returns the source recovery report.
    """
    validate_secret(secret)
    target_serializer = serializer if new_serializer is UNCHANGED else new_serializer
    target_secret = secret if new_secret is UNCHANGED else new_secret
    validate_secret(target_secret)
    validate_compression(snapshot_compression)
    source, destination = Path(src), Path(dst)
    if not source.is_dir():
        raise ConfigurationError(f"Source {str(source)!r} is not a data directory")
    existed = _empty_destination(destination)
    if destination.resolve() == source.resolve():
        raise ConfigurationError("Source and destination must be different directories")

    root: Any = _Recovering()
    inject(root, "_clock", RecordClock())
    # Hold the source writer lock so no writer appends while it is read.
    source_lock = DirectoryLock(source)
    try:
        result = recover(
            root,
            source,
            mode="strict",
            secret=secret,
            serializer=serializer,
            schemas=schemas,
            state_schemas=state_schemas,
        )
    finally:
        source_lock.release()
    system = result.system

    created = None if existed else _first_missing(destination)
    destination_lock = None
    try:
        destination.mkdir(parents=True, exist_ok=True)
        if created is not None:
            fileutils.sync_directory(created.parent)
        destination_lock = DirectoryLock(destination)
        manifest.write(
            destination, serializer=target_serializer, secret=target_secret, durability="sync"
        )
        integrity = None
        if target_secret is not None:
            integrity = Integrity.open(destination, target_secret, create=True, durability="sync")
        SnapshotManager(
            destination,
            durability="sync",
            integrity=integrity,
            serializer=target_serializer,
            compression=snapshot_compression,
        ).take_snapshot(system)
        # Prove the new directory opens with its target settings before success.
        check: Any = _Recovering()
        inject(check, "_clock", RecordClock())
        recover(
            check,
            destination,
            mode="strict",
            secret=target_secret,
            serializer=target_serializer,
            state_schemas=state_schemas,
        )
    except BaseException:
        if destination_lock is not None:
            destination_lock.release()
        if created is not None:
            shutil.rmtree(created, ignore_errors=True)
        elif destination.is_dir():
            for entry in destination.iterdir():
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
        raise
    destination_lock.release()
    return result.report
