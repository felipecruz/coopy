"""Observe synchronization and inject failures at the real journal boundary."""

import os
import pickle
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from coopy import fileutils
from coopy.base import init_persistent_system
from coopy.decorators import readonly
from coopy.journal import PersistenceError
from coopy.restore import RecoveryError

from .test_recovery_policy import Ledger


class QueryLedger(Ledger):
    @readonly
    def count(self):
        return len(self.values)


class FaultFile:
    def __init__(self, wrapped, fault):
        self.wrapped = wrapped
        self.fault = fault

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def write(self, data):
        if self.fault == "write":
            raise OSError("injected write")
        if self.fault in ("short", "partial"):
            size = self.wrapped.write(data[: len(data) // 2])
            self.wrapped.flush()
            if self.fault == "partial":
                raise OSError("injected partial write")
            return size
        return self.wrapped.write(data)

    def flush(self):
        if self.fault == "flush":
            raise OSError("injected flush")
        return self.wrapped.flush()


@pytest.mark.parametrize(
    "durability,fault",
    [
        (mode, fault)
        for mode in ("buffered", "sync")
        for fault in ("write", "short", "partial", "flush", "fsync")
        if mode == "sync" or fault != "fsync"
    ],
)
def test_persistence_fault_never_acknowledges_and_disables_writes(
    tmp_path, monkeypatch, durability, fault
):
    proxy = init_persistent_system(Ledger, str(tmp_path), durability=durability)
    journal = proxy.publisher.subscribers[0]
    original = journal.file.file
    with monkeypatch.context() as patch:
        if fault == "fsync":

            def fail_sync(fd):
                raise OSError("injected fsync")

            patch.setattr(os, "fsync", fail_sync)
        else:
            journal.file.file = FaultFile(original, fault)
        with pytest.raises(PersistenceError, match="memory may already be changed") as caught:
            proxy.add("changed")
        assert isinstance(caught.value.__cause__, OSError)
        assert proxy.values == ["changed"]
        with pytest.raises(PersistenceError, match="disabled"):
            proxy.add("must not run")
        assert proxy.values == ["changed"]
        with pytest.raises(PersistenceError, match="disabled"):
            proxy.take_snapshot()
    journal.file.file = original
    proxy.close()
    if fault in ("partial", "short"):
        with pytest.raises(RecoveryError):
            init_persistent_system(Ledger, str(tmp_path))


@pytest.mark.parametrize("durability,expected", [("buffered", 0), ("sync", 1)])
def test_sync_is_after_entire_record_and_before_return(tmp_path, monkeypatch, durability, expected):
    proxy = init_persistent_system(QueryLedger, str(tmp_path), durability=durability)
    journal = proxy.publisher.subscribers[0]
    calls = []
    real_sync = os.fsync

    def observe(fd):
        # Large payload makes Pickler.write run multiple times. Sync must see
        # the entire decodable record, not an intermediate write fragment.
        with open(journal.file.name, "rb") as file:
            record = pickle.load(file)
        assert record.args == ("x" * 200000,)
        calls.append(fd)
        real_sync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", observe)
        assert proxy.add("x" * 200000) is None
        assert len(calls) == expected
        assert proxy.count() == 1
        assert len(calls) == expected
    proxy.close()


def test_original_domain_exception_propagates_after_successful_sync(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, str(tmp_path), durability="sync")
    calls = []
    real_sync = os.fsync
    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", lambda fd: (calls.append(fd), real_sync(fd)))
        with pytest.raises(ValueError, match="expected domain failure"):
            proxy.fail("mutation before exception")
        assert len(calls) == 1
    proxy.close()


def test_disk_error_takes_precedence_over_domain_exception(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, str(tmp_path), durability="sync")
    with monkeypatch.context() as patch:

        def fail_sync(fd):
            raise OSError("disk failure")

        patch.setattr(os, "fsync", fail_sync)
        with pytest.raises(PersistenceError) as caught:
            proxy.fail("changed")
        assert str(caught.value.__cause__) == "disk failure"
    proxy.close()


@pytest.mark.parametrize("durability,expected", [("buffered", 0), ("sync", 1)])
def test_close_sync_and_failure_are_observable(tmp_path, monkeypatch, durability, expected):
    proxy = init_persistent_system(Ledger, str(tmp_path), durability=durability)
    calls = []

    def fail_sync(fd):
        calls.append(fd)
        raise OSError("close sync failed")

    monkeypatch.setattr(os, "fsync", fail_sync)
    if expected:
        with pytest.raises(PersistenceError, match="No rollback"):
            proxy.close()
    else:
        proxy.close()
    assert len(calls) == expected
    assert proxy.publisher.subscribers[0].file.closed


def test_sync_creation_rotation_and_snapshot_sync_directory(tmp_path, monkeypatch):
    events = []
    real_sync = os.fsync

    def observe(fd):
        events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        real_sync(fd)

    monkeypatch.setattr(os, "fsync", observe)
    data = tmp_path / "new"
    proxy = init_persistent_system(Ledger, str(data), durability="sync")
    # parent, manifest + its directory entry, checkpoint + directory, journal directory
    assert events == ["directory", "file", "directory", "file", "directory", "directory"]
    events.clear()
    proxy.publisher.subscribers[0].file.max_size = 1
    proxy.add("rotated")
    assert events == ["file", "file", "directory"]
    events.clear()
    proxy.take_snapshot()
    assert events == ["file", "file", "directory", "directory"]
    proxy.close()


def test_rotation_directory_failure_is_not_acknowledged(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, str(tmp_path), durability="sync")
    proxy.publisher.subscribers[0].file.max_size = 1
    with monkeypatch.context() as patch:

        def fail_directory(directory):
            raise OSError("directory sync failed")

        patch.setattr(fileutils, "sync_directory", fail_directory)
        with pytest.raises(PersistenceError):
            proxy.add("possibly persisted")
        with pytest.raises(PersistenceError):
            proxy.add("refused")
    proxy.close()
    restored = init_persistent_system(Ledger, str(tmp_path), durability="sync")
    assert restored.values == ["possibly persisted"]
    restored.close()


def test_setup_directory_sync_failure_does_not_return_proxy(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, str(tmp_path))
    proxy.close()

    def fail_directory(directory):
        raise OSError("directory sync failed")

    monkeypatch.setattr(fileutils, "sync_directory", fail_directory)
    with pytest.raises(PersistenceError):
        init_persistent_system(Ledger, str(tmp_path), durability="sync")


def test_restart_in_fresh_process_after_rotation_and_checkpoint(tmp_path):
    root = str(Path(__file__).resolve().parents[2])
    env = dict(os.environ, PYTHONPATH=root)
    script = """
import os
from coopy.base import init_persistent_system
from tests.functional.test_recovery_policy import Ledger
p = init_persistent_system(Ledger, "data", durability="sync")
p.publisher.subscribers[0].file.max_size = 1
p.add("A")
p.take_snapshot()
p.add("B")
p.add("C")
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, check=True, timeout=20)
    script = """
from coopy.base import init_persistent_system
from tests.functional.test_recovery_policy import Ledger
p = init_persistent_system(Ledger, "data", durability="sync")
assert p.values == ["A", "B", "C"]
p.add("D")
p.close()
p = init_persistent_system(Ledger, "data", durability="sync")
assert p.values == ["A", "B", "C", "D"]
p.close()
"""
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env, check=True, timeout=20)


def test_invalid_durability_does_not_initialize_storage(tmp_path):
    with pytest.raises(ValueError, match="durability"):
        init_persistent_system(Ledger, str(tmp_path), durability="sometimes")
    assert not list(tmp_path.iterdir())


def test_checkpoint_directory_sync_failure_preserves_recovery(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, str(tmp_path), durability="sync")
    proxy.add("before")
    previous = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    real_sync = fileutils.sync_directory
    calls = 0

    def fail_publication_sync(directory):
        nonlocal calls
        calls += 1
        if calls == 2:  # after journal rotation and checkpoint rename
            raise OSError("checkpoint directory sync failed")
        real_sync(directory)

    with monkeypatch.context() as patch:
        patch.setattr(fileutils, "sync_directory", fail_publication_sync)
        with pytest.raises(OSError, match="checkpoint directory sync failed"):
            proxy.take_snapshot()
    for name, data in previous.items():
        assert (tmp_path / name).read_bytes() == data
    assert len(list(tmp_path.glob("snapshot_*.dat"))) == 2
    proxy.add("after")
    proxy.close()
    restored = init_persistent_system(Ledger, str(tmp_path), durability="sync")
    assert restored.values == ["before", "after"]
    restored.close()
