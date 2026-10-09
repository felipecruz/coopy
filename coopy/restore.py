"""Strict recovery and explicit, non-writing salvage of trusted pickle storage."""
from pathlib import Path
from coopy.error import CoopyError, ConfigurationError

from typing import Generic, TypeVar

T = TypeVar("T")

from dataclasses import dataclass, field
from io import BytesIO
from pickle import Unpickler

from coopy import fileutils
from coopy.snapshot import SnapshotManager
from coopy.foundation import Action, RestoreClock
from coopy.integrity import Integrity, IntegrityError, IDENTITY_FILE, validate_secret


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
        super().__init__(f"Recovery stopped: {issue.kind} at "
                         f"{issue.position.file}:{issue.position.offset} "
                         f"(record {issue.position.record}): {issue.detail}")


def recover(system, basedir, mode='strict', *, secret=None):
    """Replay in order, stopping at the first detected defect.

    Strict mode raises without returning state. Salvage returns an inspection
    result, never a writable proxy. A divergent method may already have changed
    that result's state; the report marks it and excludes it from replayed.
    """
    validate_secret(secret)
    if mode not in ('strict', 'salvage'):
        raise ConfigurationError("recovery must be 'strict' or 'salvage'")
    basedir = Path(basedir)
    current_clock = system._clock
    report = RecoveryReport()
    recovered = None

    def stop(position, kind, error, changed=False):
        report.stop = RecoveryIssue(position, kind, str(error), changed)
        if mode == 'strict':
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
            position = RecoveryPosition(str(basedir / (report.checkpoint or '')), 0, 0)
            if report.checkpoint is None:
                raise IntegrityError('Missing signed checkpoint')
            with open(position.file, 'rb') as file:
                snapshot = BytesIO(file.read())
            snapshot_payload = integrity.read(snapshot, position.file)
            if snapshot.read(1):
                raise IntegrityError('Trailing bytes after signed snapshot')
            files = fileutils.last_log_files(basedir) or []
            for filename in files:
                position = RecoveryPosition(filename, 0, 1)
                with open(filename, 'rb') as file:
                    data = file.read()
                journal = BytesIO(data)
                record = 0
                while journal.tell() < len(data):
                    position = RecoveryPosition(filename, journal.tell(), record + 1)
                    integrity.read(journal, filename)
                    record += 1
                verified_journals[filename] = data
        except Exception as error:
            return stop(position, 'verification', error)

    try:
        if integrity is None:
            report.checkpoint = fileutils.last_snapshot_file(basedir)
            recovered = SnapshotManager(basedir).recover_snapshot()
        else:
            recovered = Unpickler(BytesIO(snapshot_payload)).load()
        if recovered is None:
            raise ValueError('No usable checkpoint found')
    except Exception as error:
        return stop(RecoveryPosition(str(basedir / (report.checkpoint or '')), 0, 0),
                    'checkpoint', error)

    try:
        try:
            files = (list(verified_journals) if integrity is not None
                     else fileutils.last_log_files(basedir) or [])
        except Exception as error:
            return stop(RecoveryPosition(str(basedir), 0, 0), 'read', error)
        for filename in files:
            position = RecoveryPosition(filename, 0, 1)
            try:
                with (BytesIO(verified_journals[filename]) if integrity is not None
                      else open(filename, 'rb')) as journal:
                    unpickler = Unpickler(journal)
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
                                action = Unpickler(BytesIO(payload)).load()
                            if not isinstance(action, Action):
                                raise ValueError('Journal record is not an Action')
                            if not isinstance(action.action, str):
                                raise ValueError('Action name is not a string')
                            if not isinstance(action.args, (tuple, list)) or not isinstance(action.kwargs, dict):
                                raise ValueError('Invalid action arguments')
                            raised = getattr(action, 'raised', None)
                            if raised is not None and type(raised) is not bool:
                                raise ValueError('Invalid action outcome metadata')
                        except Exception as error:
                            return stop(position, 'decode', error)
                        record += 1
                        position = RecoveryPosition(filename, position.offset, record,
                                                    action.action)
                        if raised is None:
                            report.legacy_actions.append(position)
                        # A missing method is not an expected domain exception.
                        try:
                            method = getattr(recovered, action.action)
                            if not callable(method):
                                raise TypeError('Action method is not callable')
                            recovered._clock = RestoreClock(getattr(action, 'results', None) or [])
                        except Exception as error:
                            return stop(position, 'method', error)
                        try:
                            method(*action.args, **action.kwargs)
                        except Exception as error:
                            if raised is not True:
                                return stop(position, 'outcome', error, changed=True)
                            report.expected_failures += 1
                        else:
                            if raised is True:
                                return stop(position, 'outcome', ValueError(
                                    'Originally failing action now succeeded'), changed=True)
                        report.replayed += 1
            except RecoveryError:
                raise
            except Exception as error:
                return stop(position, 'read', error)
        return RecoveryResult(recovered, report)
    finally:
        recovered._clock = current_clock


def restore(system, basedir, *, secret=None):
    """Compatibility entry point, now strict; use recover for reports/salvage."""
    return recover(system, basedir, secret=secret).system
