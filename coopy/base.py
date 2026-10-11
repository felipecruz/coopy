"""
Created on Dec 6, 2011

@author: felipe j. cruz
"""

from __future__ import annotations

__author__ = "Felipe Cruz <felipecruz@gmail.com>"
__license__ = "BSD"

import logging
import math
import os
import threading
import time
import warnings
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any, Generic, Literal, TypeVar, cast, overload

from coopy import __version__ as __version__
from coopy import fileutils, manifest
from coopy.environment import Env, RecordEnv
from coopy.error import ConfigurationError, LifecycleError, ReplicationError
from coopy.foundation import Action, Clock, Publisher, RecordClock
from coopy.integrity import IDENTITY_FILE, Integrity, Secret, validate_secret
from coopy.journal import DiskJournal
from coopy.locking import DirectoryLock
from coopy.network.default_select import CopyNet, CopyNetSlave
from coopy.prune import PruneReport, prune_files, validate_prune
from coopy.restore import RecoveryReport, RecoveryResult, recover
from coopy.serialization import ActionSchemas, Serializer, StateSchemas
from coopy.snapshot import SnapshotJob, SnapshotManager, SnapshotTimer, fork_supported
from coopy.utils import action_check, inject, method_or_none
from coopy.validation import check_policy, validate_system

CORE_LOG_PREFIX = "[CORE] "
DEFAULT_PASSWORD = b"copynet"

logger = logging.getLogger("coopy")
logger.addHandler(logging.NullHandler())


def logging_config(basedir: PathLike = "./") -> None:
    log_file_path = os.path.abspath(os.path.join(basedir, "coopy.log"))
    result = logging.getLogger("coopy")
    result.setLevel(logging.DEBUG)

    # avoid duplicated log lines when called more than once
    for handler in result.handlers:
        if getattr(handler, "baseFilename", None) == log_file_path:
            return

    handler = RotatingFileHandler(log_file_path, "a", 1000000, 10)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", "%a, %d %b %Y %H:%M:%S"
    )
    handler.setFormatter(formatter)
    result.addHandler(handler)


def _to_password(password: str | bytes | None) -> bytes:
    if password is None:
        return DEFAULT_PASSWORD
    if isinstance(password, str):
        return password.encode("utf-8")
    return password


T = TypeVar("T")
PathLike = str | os.PathLike[str]


@overload
def init_persistent_system(
    obj: type[T],
    basedir: PathLike | None = None,
    *,
    recovery: Literal["strict"] = "strict",
    durability: Literal["buffered", "sync"] = "buffered",
    secret: Secret | None = None,
    snapshot_compression: str | None = None,
    group_commit_delay: float = 0.0,
    serializer: Serializer | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
    validation: Literal["warn", "strict", "off"] = "warn",
) -> T: ...


@overload
def init_persistent_system(
    obj: T,
    basedir: PathLike | None = None,
    *,
    recovery: Literal["strict"] = "strict",
    durability: Literal["buffered", "sync"] = "buffered",
    secret: Secret | None = None,
    snapshot_compression: str | None = None,
    group_commit_delay: float = 0.0,
    serializer: Serializer | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
    validation: Literal["warn", "strict", "off"] = "warn",
) -> T: ...


@overload
def init_persistent_system(
    obj: type[T],
    basedir: PathLike | None = None,
    *,
    recovery: Literal["salvage"],
    durability: Literal["buffered", "sync"] = "buffered",
    secret: Secret | None = None,
    snapshot_compression: str | None = None,
    group_commit_delay: float = 0.0,
    serializer: Serializer | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
    validation: Literal["warn", "strict", "off"] = "warn",
) -> RecoveryResult[T]: ...


@overload
def init_persistent_system(
    obj: T,
    basedir: PathLike | None = None,
    *,
    recovery: Literal["salvage"],
    durability: Literal["buffered", "sync"] = "buffered",
    secret: Secret | None = None,
    snapshot_compression: str | None = None,
    group_commit_delay: float = 0.0,
    serializer: Serializer | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
    validation: Literal["warn", "strict", "off"] = "warn",
) -> RecoveryResult[T]: ...


@overload
def init_persistent_system(
    obj: type[T],
    basedir: PathLike | None = None,
    *,
    recovery: str,
    durability: str = "buffered",
    secret: Secret | None = None,
    snapshot_compression: str | None = None,
    group_commit_delay: float = 0.0,
    serializer: Serializer | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
    validation: str = "warn",
) -> T | RecoveryResult[T]: ...
@overload
def init_persistent_system(
    obj: T,
    basedir: PathLike | None = None,
    *,
    recovery: str,
    durability: str = "buffered",
    secret: Secret | None = None,
    snapshot_compression: str | None = None,
    group_commit_delay: float = 0.0,
    serializer: Serializer | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
    validation: str = "warn",
) -> T | RecoveryResult[T]: ...


def init_persistent_system(
    obj: Any,
    basedir: PathLike | None = None,
    *,
    recovery: str = "strict",
    durability: str = "buffered",
    secret: Secret | None = None,
    snapshot_compression: str | None = None,
    group_commit_delay: float = 0.0,
    serializer: Serializer | None = None,
    schemas: ActionSchemas | None = None,
    state_schemas: StateSchemas | None = None,
    validation: str = "warn",
) -> Any:
    validate_secret(secret)
    if not math.isfinite(group_commit_delay) or group_commit_delay < 0:
        raise ConfigurationError("group_commit_delay must be finite and nonnegative")
    from coopy.compression import validate_compression

    validate_compression(snapshot_compression)
    if recovery not in ("strict", "salvage"):
        raise ConfigurationError("recovery must be 'strict' or 'salvage'")
    if durability not in ("buffered", "sync"):
        raise ConfigurationError("durability must be 'buffered' or 'sync'")
    check_policy(validation)

    # a system object is needed in order to coopy work
    if obj is None:
        raise ConfigurationError(
            CORE_LOG_PREFIX + "Must input a valid object if there's no snapshot files"
        )

    # if obj is a class, change obj to an insance
    if isinstance(obj, type):
        obj = obj()

    validate_system(obj, validation)

    # first step is to check basedir argument. if isn't defined
    # coopy will create a directory name based on system class
    if not basedir:
        basedir = fileutils.obj_to_dir_name(obj)

    # convert some string to a valid directory name
    basedir = Path(basedir)

    system_data_path = os.getcwd()

    # Salvage inspects existing storage without creating checkpoints/journals.
    if recovery == "salvage":
        inject(obj, "_clock", RecordClock())
        return recover(
            obj,
            basedir,
            mode="salvage",
            secret=secret,
            serializer=serializer,
            schemas=schemas,
            state_schemas=state_schemas,
        )

    # check if basedir exists, if not, create it
    try:
        basedir.stat()
    except os.error:
        basedir.mkdir(parents=True, exist_ok=True)
        if durability == "sync":
            fileutils.sync_directory(os.path.dirname(os.path.abspath(basedir)))

    # Writable systems own the directory until close() or process exit.
    directory_lock = DirectoryLock(basedir)
    try:
        proxy = _open_writable(
            obj,
            basedir,
            system_data_path,
            recovery=recovery,
            durability=durability,
            secret=secret,
            snapshot_compression=snapshot_compression,
            group_commit_delay=group_commit_delay,
            serializer=serializer,
            schemas=schemas,
            state_schemas=state_schemas,
        )
    except BaseException:
        directory_lock.release()
        raise
    proxy._directory_lock = directory_lock
    return proxy


def _open_writable(
    obj: Any,
    basedir: Path,
    system_data_path: str,
    *,
    recovery: str,
    durability: str,
    secret: Secret | None,
    snapshot_compression: str | None,
    group_commit_delay: float,
    serializer: Serializer | None,
    schemas: ActionSchemas | None,
    state_schemas: StateSchemas | None,
) -> CoopyProxy:
    # Runs under the directory lock, so the manifest has a single writer.
    existing = manifest.check(basedir, serializer=serializer, secret=secret)
    empty = (
        not fileutils.list_snapshot_files(basedir)
        and not fileutils.list_log_files(basedir)
        and not os.path.exists(os.path.join(basedir, IDENTITY_FILE))
    )
    if existing is None and empty:
        manifest.write(basedir, serializer=serializer, secret=secret, durability=durability)

    # if no snapshot files, create first one with a 'empty' system
    integrity = None
    new_signed = secret is not None and empty
    if new_signed:
        assert secret is not None
        integrity = Integrity.open(basedir, secret, create=True, durability=durability)
    if not fileutils.last_snapshot_file(basedir) and (secret is None or new_signed):
        logger.info(CORE_LOG_PREFIX + "No snapshot files..")
        SnapshotManager(
            basedir,
            durability=durability,
            integrity=integrity,
            serializer=serializer,
            compression=snapshot_compression,
        ).take_snapshot(obj)

    # measure restore time
    start = time.perf_counter()
    logger.info(CORE_LOG_PREFIX + "coopy init....")

    # inject clock on system object
    inject(obj, "_clock", RecordClock())
    inject(obj, "_system_data_path", system_data_path)

    # RestoreHelper will recover a system state based on snapshots and
    # transations files extracting actions executed previously and
    # re-executing them again
    result = recover(
        obj,
        basedir,
        mode=recovery,
        secret=secret,
        serializer=serializer,
        schemas=schemas,
        state_schemas=state_schemas,
    )
    obj = result.system
    if not empty and (existing is None or existing["format_version"] < manifest.FORMAT_VERSION):
        # An older directory restored cleanly; new records use the current format.
        manifest.write(basedir, serializer=serializer, secret=secret, durability=durability)

    delta = time.perf_counter() - start
    logger.info(CORE_LOG_PREFIX + "restore spent %.6f seconds" % delta)

    if secret is not None:
        integrity = Integrity.open(basedir, secret)
    journal = DiskJournal(
        basedir, system_data_path, durability=durability, integrity=integrity, serializer=serializer
    )
    journal.setup()

    snapshot_manager = SnapshotManager(
        basedir,
        durability=durability,
        integrity=integrity,
        serializer=serializer,
        compression=snapshot_compression,
    )

    proxy = CoopyProxy(
        obj,
        [journal],
        snapshot_manager=snapshot_manager,
        schemas=schemas,
        group_commit_delay=group_commit_delay,
    )
    proxy.recovery_report = result.report
    return proxy


def init_system(obj: Any, subscribers: list[Any]) -> CoopyProxy:
    # return a coopy proxy instead of a system instance
    proxy = CoopyProxy(obj, subscribers)
    return proxy


class CoopyProxy:
    def __init__(
        self,
        obj: Any,
        subscribers: list[Any],
        snapshot_manager: SnapshotManager | None = None,
        schemas: ActionSchemas | None = None,
        group_commit_delay: float = 0.0,
    ) -> None:
        self.schemas = schemas if schemas is not None else ActionSchemas()
        self._closed = False
        self.recovery_report = RecoveryReport()
        self.server: Any = None
        self.obj = obj
        self.publisher = Publisher(subscribers)
        self.lock = threading.RLock()
        for subscriber in subscribers:
            if isinstance(subscriber, DiskJournal):
                subscriber.enable_group_commit(self.lock, group_commit_delay)
        self.master: Any = None
        self.slave: Any = None
        self.snapshot_manager = snapshot_manager
        self.snapshot_timer: SnapshotTimer | None = None
        self._snapshot_job: SnapshotJob | None = None
        self._directory_lock: DirectoryLock | None = None
        # values for self._clock; None reads the system clock
        self._clock_source: Clock | None = None
        # values for self._env; None reads OS entropy
        self._env_source: Env | None = None

    def start_snapshot_manager(self, snapshot_time: float) -> None:
        # the timer waits snapshot_time before the first snapshot, so this
        # call returns immediately
        self._check_open()
        if self.snapshot_timer is not None:
            raise LifecycleError("Snapshot timer is already started")
        self.snapshot_timer = SnapshotTimer(snapshot_time, control(self))
        self.snapshot_timer.start()

    def start_master(
        self,
        port: int = 8012,
        password: str | bytes | None = None,
        ipc: bool = False,
        host: str = "127.0.0.1",
    ) -> None:
        warnings.warn(
            "start_master is deprecated; use start_primary (removal: v0.9)",
            DeprecationWarning,
            stacklevel=2,
        )
        CoopyProxy.start_primary(self, port, password, ipc, host)

    def start_slave(
        self, host: str, port: int, password: str | bytes | None = None, ipc: bool = False
    ) -> Any:
        warnings.warn(
            "start_slave is deprecated; use start_replica (removal: v0.9)",
            DeprecationWarning,
            stacklevel=2,
        )
        return CoopyProxy.start_replica(self, host, port, password, ipc)

    def start_primary(
        self,
        port: int = 8012,
        password: str | bytes | None = None,
        ipc: bool = False,
        host: str = "127.0.0.1",
    ) -> None:
        with self.lock:
            self._check_open()
            if self.slave is not None:
                raise ReplicationError("Cannot promote a slave to master.")
            if self.master is not None:
                raise ReplicationError("Master is already started.")
            self.server = CopyNet(
                self.obj,
                host=host,
                port=port,
                password=_to_password(password),
                ipc=ipc,
                lock=self.lock,
            )
            self.publisher.register(self.server)
            self.master = self.server
            self.server.start()

    def start_replica(
        self, host: str, port: int, password: str | bytes | None = None, ipc: bool = False
    ) -> Any:
        with self.lock:
            self._check_open()
            if self.master is not None:
                raise ReplicationError("Cannot start a slave on an active master.")
            if self.slave is not None and self.slave.is_alive():
                raise ReplicationError("Slave receiver is already started; close it first.")
            self.server = None
            # Install the read/write guard before attempting network I/O, so
            # even a failed connection leaves an explicitly unsynchronized slave.
            self.slave = CopyNetSlave(
                self, host=host, port=port, password=_to_password(password), ipc=ipc, connect=False
            )
            self.slave._connect()
            self.slave.start()
            return self.slave

    def __getattribute__(self, name: str) -> Any:
        if name in _CONTROL_NAMES:
            obj = object.__getattribute__(self, "obj")
            if hasattr(obj, name):
                return self.__getattr__(name)
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> Any:
        self._check_open()
        if self.slave and not self.slave.synchronized:
            raise ReplicationError("Slave is not synchronized with its master.")
        domain_method = method_or_none(self.obj, name)

        if not domain_method:
            return getattr(self.obj, name)

        (readonly, unlocked, abort_exception) = action_check(domain_method)

        # TODO: re-write
        if not readonly and hasattr(self, "slave") and self.slave:
            raise ReplicationError("This is a slave/read-only instance.")

        # Grouped synchronous writes must hold the shared condition lock even
        # for an explicitly unlocked domain method.
        locked = not unlocked or (
            not readonly
            and any(
                isinstance(j, DiskJournal) and j.condition is not None
                for j in self.publisher.subscribers
            )
        )

        def method(*args: Any, **kwargs: Any) -> Any:
            exception = None
            env = None
            try:
                if locked:
                    self.lock.acquire(True)

                self._check_open()
                if self.slave and not self.slave.synchronized:
                    raise ReplicationError("Slave is not synchronized with its master.")
                if self.slave and not readonly:
                    raise ReplicationError("This is a slave/read-only instance.")

                # record all calls to clock.now()
                clock = RecordClock(self._clock_source)
                self.obj._clock = clock
                # self._env exists only during the call, so snapshots never hold it
                env = RecordEnv(clock, self._env_source)
                inject(self.obj, "_env", env)

                thread_ident = threading.get_ident()
                action = Action(thread_ident, name, datetime.now(), args, kwargs)
                action.schema_version = self.schemas.version(name)
                system = None
                if not readonly:
                    self.publisher.publish_before(action)

                try:
                    system = action.execute_action(self.obj)
                except Exception as e:
                    logger.debug(CORE_LOG_PREFIX + "Error: " + str(e))
                    if abort_exception:
                        logger.debug(CORE_LOG_PREFIX + "Aborting action" + str(action))
                    if not abort_exception:
                        self.publisher.publish_exception(action)
                    exception = e

                # restore clock
                action.results = clock.results
                # keep a test clock out of snapshots of the domain
                vars(clock).pop("source", None)
                # group commit releases the lock while waiting, so drop _env now
                if vars(self.obj).get("_env") is env:
                    del vars(self.obj)["_env"]
                # lets restore tell expected failures from divergences
                action.raised = exception is not None

                if not readonly and not (abort_exception and action.raised):
                    try:
                        self.publisher.publish(action)
                    finally:
                        for journal in self.publisher.subscribers:
                            if isinstance(journal, DiskJournal):
                                journal.wait_sync()

            finally:
                if env is not None and vars(self.obj).get("_env") is env:
                    del vars(self.obj)["_env"]
                if locked:
                    self.lock.release()

            if exception is not None:
                raise exception

            return system

        return method

    def basedir_abspath(self) -> list[str]:
        disk_journals = (
            journal for journal in self.publisher.subscribers if hasattr(journal, "basedir")
        )
        return [
            os.path.join(os.path.abspath(os.getcwd()), journal.basedir) for journal in disk_journals
        ]

    def take_snapshot(
        self, *, mode: str = "blocking", fork_safe: bool = False
    ) -> SnapshotJob | None:
        if mode not in ("blocking", "fork"):
            raise ConfigurationError("snapshot mode must be 'blocking' or 'fork'")
        slave = self.slave
        if slave:
            slave.acquire()
        try:
            self.lock.acquire()
            try:
                self._check_open()
                if self._snapshot_job is not None and not self._snapshot_job.done:
                    raise LifecycleError("Call snapshot_job.wait() before another snapshot")
                if slave and not slave.synchronized:
                    raise ReplicationError("Cannot snapshot an unsynchronized slave.")
                if self.snapshot_manager:
                    for journal in self.publisher.subscribers:
                        if isinstance(journal, DiskJournal):
                            journal.check_writable()

                    def advance_journals(destination: str) -> None:
                        for journal in self.publisher.subscribers:
                            if isinstance(journal, DiskJournal):
                                journal.checkpoint(destination)

                    if mode == "fork":
                        if fork_supported(fork_safe) and not self.master and not slave:
                            self._snapshot_job = self.snapshot_manager.start_fork(
                                self.obj, advance_journals
                            )
                            return self._snapshot_job
                        warnings.warn(
                            "Fork snapshot unavailable or not declared safe; using blocking snapshot",
                            RuntimeWarning,
                            stacklevel=2,
                        )
                    self.snapshot_manager.take_snapshot(self.obj, before_publish=advance_journals)
            finally:
                self.lock.release()
        finally:
            if slave:
                slave.release()
        return None

    def _check_open(self) -> None:
        if self._closed:
            raise LifecycleError("Persistent system is closed")

    def __enter__(self) -> Any:
        self._check_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            CoopyProxy.close(self)
        except Exception:
            if exc is None:
                raise
            logger.exception("Cleanup failed while propagating context exception")

    def close(self) -> None:
        errors: list[Exception] = []
        with self.lock:
            if self._closed:
                return
            for journal in self.publisher.subscribers:
                if isinstance(journal, DiskJournal) and journal.failure is None:
                    try:
                        journal.sync_pending()
                    except Exception as error:
                        errors.append(error)
            self._closed = True
        # Never join worker threads while holding their domain lock.
        if self._snapshot_job is not None:
            try:
                self._snapshot_job.wait()
            except Exception as error:
                errors.append(error)
        if self.snapshot_timer:
            try:
                self.snapshot_timer.stop()
            except Exception as error:
                errors.append(error)
            self.snapshot_timer = None
        for resource in list(self.publisher.subscribers) + ([self.slave] if self.slave else []):
            try:
                resource.close()
            except Exception as error:
                errors.append(error)
        if self._directory_lock is not None:
            try:
                self._directory_lock.release()
            except Exception as error:
                errors.append(error)
        if errors:
            raise errors[0]

    def shutdown(self) -> None:
        if self.master:
            self.master.close()
            self.master = None
        if self.slave:
            self.slave.close()
            # Retain the slave role and guard until a fresh bootstrap succeeds.


_CONTROL_NAMES = frozenset(
    {
        "take_snapshot",
        "close",
        "shutdown",
        "start_snapshot_manager",
        "start_master",
        "start_slave",
        "start_primary",
        "start_replica",
        "basedir_abspath",
    }
)


class PersistenceControl(Generic[T]):
    """Persistence operations, independent of domain method names."""

    def __init__(self, proxy: CoopyProxy) -> None:
        self._proxy = proxy

    def __enter__(self) -> T:
        return cast(T, self._proxy.__enter__())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._proxy.__exit__(exc_type, exc, traceback)

    @property
    def recovery_report(self) -> RecoveryReport:
        return self._proxy.recovery_report

    def take_snapshot(
        self, *, mode: str = "blocking", fork_safe: bool = False
    ) -> SnapshotJob | None:
        return CoopyProxy.take_snapshot(self._proxy, mode=mode, fork_safe=fork_safe)

    def close(self) -> None:
        CoopyProxy.close(self._proxy)

    def prune(self, *, keep: int, keep_for: timedelta | None = None) -> PruneReport:
        """Delete checkpoints older than the newest ``keep`` and unneeded journals.

        Checkpoints published within ``keep_for`` are also kept. Journals are
        removed only when they precede the oldest kept checkpoint, so the
        current state and every kept checkpoint stay recoverable. Runs under the
        domain lock: writes and blocking snapshots wait until it returns.
        """
        validate_prune(keep, keep_for)
        proxy = self._proxy
        with proxy.lock:
            proxy._check_open()
            if proxy.snapshot_manager is None:
                raise LifecycleError("prune() requires a system with a data directory")
            return prune_files(proxy.snapshot_manager.basedir, keep=keep, keep_for=keep_for)

    def shutdown(self) -> None:
        CoopyProxy.shutdown(self._proxy)

    def start_snapshot_manager(self, snapshot_time: float) -> None:
        CoopyProxy.start_snapshot_manager(self._proxy, snapshot_time)

    def start_master(
        self,
        port: int = 8012,
        password: str | bytes | None = None,
        ipc: bool = False,
        host: str = "127.0.0.1",
    ) -> None:
        warnings.warn(
            "start_master is deprecated; use start_primary (removal: v0.9)",
            DeprecationWarning,
            stacklevel=2,
        )
        PersistenceControl.start_primary(self, port, password, ipc, host)

    def start_slave(
        self, host: str, port: int, password: str | bytes | None = None, ipc: bool = False
    ) -> Any:
        warnings.warn(
            "start_slave is deprecated; use start_replica (removal: v0.9)",
            DeprecationWarning,
            stacklevel=2,
        )
        return PersistenceControl.start_replica(self, host, port, password, ipc)

    def start_primary(
        self,
        port: int = 8012,
        password: str | bytes | None = None,
        ipc: bool = False,
        host: str = "127.0.0.1",
    ) -> None:
        CoopyProxy.start_primary(self._proxy, port, password, ipc, host)

    def start_replica(
        self, host: str, port: int, password: str | bytes | None = None, ipc: bool = False
    ) -> Any:
        return CoopyProxy.start_replica(self._proxy, host, port, password, ipc)

    def basedir_abspath(self) -> list[str]:
        return CoopyProxy.basedir_abspath(self._proxy)


def control(system: T) -> PersistenceControl[T]:
    """Return persistence controls for a writable coopy system."""
    if not isinstance(system, CoopyProxy):
        raise TypeError("control() requires a writable coopy system, not a salvage result")
    return PersistenceControl(system)
