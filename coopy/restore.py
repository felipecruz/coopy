"""Strict recovery and explicit, non-writing salvage of serialized storage."""

import copy
import inspect
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from pickle import Unpickler
from typing import Generic, TypeVar

from coopy import fileutils, manifest
from coopy.environment import RestoreEnv
from coopy.error import ClockDivergenceError, ConfigurationError, CoopyError
from coopy.foundation import Action, RestoreClock
from coopy.integrity import IDENTITY_FILE, Integrity, IntegrityError, validate_secret
from coopy.snapshot import SnapshotManager

T = TypeVar("T")


@dataclass(frozen=True)
class RecoveryPosition:
    file: str
    offset: int
    record: int  # one-based within the file; zero denotes a snapshot
    action: str | None = None


@dataclass(frozen=True)
class RecoveryIssue:
    position: RecoveryPosition
    kind: str
    detail: str
    state_may_be_changed: bool = False


@dataclass
class RecoveryReport:
    checkpoint: str | None = None
    replayed: int = 0
    expected_failures: int = 0
    legacy_actions: list[RecoveryPosition] = field(default_factory=list)
    stop: RecoveryIssue | None = None
    bounded: bool = False

    @property
    def complete(self):
        """Reached the end; legacy outcomes may still be unverifiable."""
        return self.stop is None


@dataclass
class RecoveryResult(Generic[T]):
    system: T | None
    report: RecoveryReport


class RecoveryError(CoopyError, RuntimeError):
    def __init__(self, report):
        self.report = report
        issue = report.stop
        super().__init__(
            f"Recovery stopped: {issue.kind} at "
            f"{issue.position.file}:{issue.position.offset} "
            f"(record {issue.position.record}): {issue.detail}"
        )


def recover(
    system,
    basedir,
    mode="strict",
    *,
    secret=None,
    serializer=None,
    schemas=None,
    state_schemas=None,
    until=None,
):
    """Replay in order, stopping at the first detected defect.

    Strict mode raises without returning state. Salvage returns an inspection
    result, never a writable proxy. A divergent method may already have changed
    that result's state; the report marks it and excludes it from replayed.

    ``until`` limits replay to a point in time. An ``int`` stops after that
    many actions (one-based); a ``datetime`` stops before the first action
    whose timestamp exceeds the bound. Bounds before the oldest kept
    checkpoint raise ``ConfigurationError``.
    """
    from coopy.serialization import ActionSchemas, StateSchemas

    schemas = schemas if schemas is not None else ActionSchemas()
    state_schemas = state_schemas if state_schemas is not None else StateSchemas()
    validate_secret(secret)
    if mode not in ("strict", "salvage"):
        raise ConfigurationError("recovery must be 'strict' or 'salvage'")
    if until is not None and not isinstance(until, (int, datetime)):
        raise ConfigurationError("until must be an int (action count) or a datetime")
    if isinstance(until, int) and until < 1:
        raise ConfigurationError("until action count must be >= 1")
    basedir = Path(basedir)
    # Newer formats and mismatched settings fail before anything is decoded.
    manifest.check(basedir, serializer=serializer, secret=secret)
    current_clock = system._clock
    report = RecoveryReport()
    recovered = None

    def stop(position, kind, error, changed=False):
        report.stop = RecoveryIssue(position, kind, str(error), changed)
        if mode == "strict":
            raise RecoveryError(report) from error
        return RecoveryResult(recovered, report)

    verified_journals = {}
    integrity = None
    if secret is not None:
        # Authenticate the entire recovery input before constructing ANY
        # Unpickler. Retain exactly these bytes to avoid a verify/reopen race.
        position = RecoveryPosition(str(basedir / IDENTITY_FILE), 0, 0)
        try:
            integrity = Integrity.open(basedir, secret)
            report.checkpoint = fileutils.last_snapshot_file(basedir)
            position = RecoveryPosition(str(basedir / (report.checkpoint or "")), 0, 0)
            if report.checkpoint is None:
                raise IntegrityError("Missing signed checkpoint")
            with open(position.file, "rb") as file:
                snapshot = BytesIO(file.read())
            snapshot_payload = integrity.read(snapshot, position.file)
            if snapshot.read(1):
                raise IntegrityError("Trailing bytes after signed snapshot")
            files = fileutils.last_log_files(basedir) or []
            for filename in files:
                position = RecoveryPosition(filename, 0, 1)
                with open(filename, "rb") as file:
                    data = file.read()
                journal = BytesIO(data)
                record = 0
                while journal.tell() < len(data):
                    position = RecoveryPosition(filename, journal.tell(), record + 1)
                    integrity.read(journal, filename)
                    record += 1
                verified_journals[filename] = data
        except Exception as error:
            return stop(position, "verification", error)

    try:
        if integrity is None:
            report.checkpoint = fileutils.last_snapshot_file(basedir)
            stored = SnapshotManager(basedir, serializer=serializer).recover_snapshot()
        else:
            stored = SnapshotManager(basedir, serializer=serializer).load_payload(snapshot_payload)
        if stored is None:
            raise ValueError("No usable checkpoint found")
        # Older snapshot state reaches the current shape before any replay.
        recovered = state_schemas.upgrade(stored)
    except Exception as error:
        return stop(
            RecoveryPosition(str(basedir / (report.checkpoint or "")), 0, 0), "checkpoint", error
        )

    try:
        try:
            files = (
                list(verified_journals)
                if integrity is not None
                else fileutils.last_log_files(basedir) or []
            )
        except Exception as error:
            return stop(RecoveryPosition(str(basedir), 0, 0), "read", error)
        for filename in files:
            position = RecoveryPosition(filename, 0, 1)
            try:
                with (
                    BytesIO(verified_journals[filename])
                    if integrity is not None
                    else open(filename, "rb")
                ) as journal:
                    unpickler = (
                        Unpickler(journal) if serializer is None else serializer.reader(journal)
                    )
                    record = 0
                    while True:
                        position = RecoveryPosition(filename, journal.tell(), record + 1)
                        # EOF is normal only BEFORE a record starts. EOFError
                        # from load() means the record was incomplete.
                        if integrity is not None:
                            at_end = journal.tell() == len(verified_journals[filename])
                        else:
                            at_end = not journal.peek(1)
                        if at_end:
                            break
                        try:
                            if integrity is None:
                                action = unpickler.load()
                            else:
                                payload = integrity.read(journal, filename)
                                action = (
                                    Unpickler(BytesIO(payload)).load()
                                    if serializer is None
                                    else serializer.loads(payload)
                                )
                            if not isinstance(action, Action):
                                raise ValueError("Journal record is not an Action")
                            if not isinstance(action.action, str):
                                raise ValueError("Action name is not a string")
                            if not isinstance(action.args, (tuple, list)) or not isinstance(
                                action.kwargs, dict
                            ):
                                raise ValueError("Invalid action arguments")
                            # Do not mutate memoized legacy records while migrating.
                            action = copy.copy(action)
                            upgraded = schemas.upgrade(action)
                            if upgraded:
                                inspect.signature(getattr(recovered, action.action)).bind(
                                    *action.args, **action.kwargs
                                )
                            raised = getattr(action, "raised", None)
                            if raised is not None and type(raised) is not bool:
                                raise ValueError("Invalid action outcome metadata")
                        except Exception as error:
                            return stop(position, "decode", error)
                        record += 1
                        position = RecoveryPosition(
                            filename, position.offset, record, action.action
                        )
                        if raised is None:
                            report.legacy_actions.append(position)
                        # Check point-in-time bound before executing.
                        if until is not None:
                            if isinstance(until, int) and report.replayed >= until:
                                report.bounded = True
                                return RecoveryResult(recovered, report)
                            if isinstance(until, datetime) and action.timestamp > until:
                                report.bounded = True
                                return RecoveryResult(recovered, report)
                        # A missing method is not an expected domain exception.
                        try:
                            method = getattr(recovered, action.action)
                            if not callable(method):
                                raise TypeError("Action method is not callable")
                            clock = RestoreClock.for_action(action)
                            recovered._clock = clock
                            vars(recovered)["_env"] = RestoreEnv(clock)
                        except Exception as error:
                            return stop(position, "method", error)
                        failure = None
                        try:
                            method(*action.args, **action.kwargs)
                        except Exception as error:
                            failure = error
                        # A clock divergence wins even if the method swallowed it.
                        try:
                            clock.check_calls()
                        except ClockDivergenceError as error:
                            return stop(position, "clock", error, changed=True)
                        if failure is not None:
                            if raised is not True:
                                return stop(position, "outcome", failure, changed=True)
                            report.expected_failures += 1
                        elif raised is True:
                            return stop(
                                position,
                                "outcome",
                                ValueError("Originally failing action now succeeded"),
                                changed=True,
                            )
                        try:
                            clock.check_complete()
                        except ClockDivergenceError as error:
                            return stop(position, "clock", error, changed=True)
                        report.replayed += 1
            except RecoveryError:
                raise
            except Exception as error:
                return stop(position, "read", error)
        return RecoveryResult(recovered, report)
    finally:
        recovered._clock = current_clock
        if recovered is not None:
            vars(recovered).pop("_env", None)


def replay(
    obj,
    basedir,
    *,
    until=None,
    secret=None,
    serializer=None,
    schemas=None,
    state_schemas=None,
):
    """Rebuild read-only state up to a bound without writing anything.

    ``until`` is an ``int`` (action count, one-based) or a ``datetime``
    (stop before the first action whose timestamp exceeds the bound).
    Returns a ``RecoveryResult`` whose ``.system`` is the rebuilt object
    and ``.report`` describes what was replayed. Nothing is written.

    Raises ``ConfigurationError`` when ``until`` falls before the oldest
    kept checkpoint.
    """
    from coopy.foundation import RecordClock
    from coopy.utils import inject

    if obj is None:
        raise ConfigurationError("Must provide a system object or class")
    if isinstance(obj, type):
        obj = obj()
    inject(obj, "_clock", RecordClock())
    return recover(
        obj,
        basedir,
        mode="salvage",
        secret=secret,
        serializer=serializer,
        schemas=schemas,
        state_schemas=state_schemas,
        until=until,
    )


def restore(system, basedir, *, secret=None, serializer=None, schemas=None, state_schemas=None):
    """Compatibility entry point, now strict; use recover for reports/salvage."""
    return recover(
        system,
        basedir,
        secret=secret,
        serializer=serializer,
        schemas=schemas,
        state_schemas=state_schemas,
    ).system
