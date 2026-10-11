"""@transactional rolls failed calls back, live and after a restart (F33)."""

import os
import pickle
import threading

import pytest

from coopy.base import CoopyProxy, init_persistent_system
from coopy.decorators import abort_exception, readonly, transactional, unlocked
from coopy.error import ConfigurationError, PersistenceError
from tests.unit.test_network_select import wait_for


class Item:
    def __init__(self, name, owner):
        self.name = name
        self.tags = []
        # a reference back to the root object
        self.owner = owner


class Store:
    def __init__(self):
        self.items = {}
        self.log = []
        self.count = 0

    def _put(self, name, fail):
        item = self.items.setdefault(name, Item(name, self))
        item.tags.append(self._clock.now())
        self.log.append(name)
        self.count += 1
        self.extra = "added during the call"
        if fail:
            raise ValueError("rejected")
        del self.extra
        return len(self.log)

    @transactional
    def put(self, name, *, fail=False):
        return self._put(name, fail)

    @abort_exception
    def put_or_abort(self, name, *, fail=False):
        return self._put(name, fail)

    def put_plain(self, name, *, fail=False):
        return self._put(name, fail)

    @transactional
    def put_many(self, names, *, fail=False):
        # nested calls on self, transactional or not, run inside this call
        for name in names:
            self.put(name)
        self.put_plain("plain")
        if fail:
            raise ValueError("rejected batch")

    @transactional
    def put_recovering(self, name):
        # an exception caught inside the call is not a failed call
        try:
            self.put(name, fail=True)
        except ValueError:
            pass
        return self.count

    @transactional
    def interrupt(self):
        self.log.append("interrupted")
        raise KeyboardInterrupt

    @readonly
    def state(self):
        return (
            {
                name: (item.name, list(item.tags), item.owner is self)
                for name, item in self.items.items()
            },
            list(self.log),
            self.count,
            hasattr(self, "extra"),
        )


def journaled(basedir):
    actions = []
    for path in sorted(basedir.glob("transaction_*.log")):
        with path.open("rb") as stream:
            unpickler = pickle.Unpickler(stream)
            while True:
                try:
                    actions.append(unpickler.load())
                except EOFError:
                    break
    return actions


def test_failed_call_restores_state_live_and_after_restart(tmp_path):
    store = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        assert store.put("a") == 1
        before = store.state()
        items, log = store.items, store.log
        with pytest.raises(ValueError, match="^rejected$"):
            store.put("a", fail=True)
        with pytest.raises(ValueError, match="^rejected$"):
            store.put("b", fail=True)
        assert store.state() == before
        # the root keeps its identity and references back to it still point at it
        assert store.obj.items["a"].owner is store.obj
        assert store.items is not items and store.log is not log
        assert store.put("c") == 2
        live = store.state()
    finally:
        store.close()

    assert [action.action for action in journaled(tmp_path)] == ["put", "put"]
    restored = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        assert restored.state() == live
        restored.take_snapshot()
    finally:
        restored.close()
    snapshotted = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        assert snapshotted.state() == live
    finally:
        snapshotted.close()


def test_successful_call_keeps_object_identity(tmp_path):
    store = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        log = store.log
        store.put("a")
        assert store.log is log and log == ["a"]
    finally:
        store.close()


def test_non_transactional_failures_still_keep_mutations(tmp_path):
    store = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        with pytest.raises(ValueError):
            store.put_or_abort("aborted", fail=True)
        with pytest.raises(ValueError):
            store.put_plain("plain", fail=True)
        assert store.log == ["aborted", "plain"]
        assert store.extra == "added during the call"
    finally:
        store.close()
    assert [(a.action, a.raised) for a in journaled(tmp_path)] == [("put_plain", True)]


def test_nested_calls_roll_back_with_the_outer_call(tmp_path):
    store = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        with pytest.raises(ValueError, match="rejected batch"):
            store.put_many(["a", "b"], fail=True)
        assert store.state() == ({}, [], 0, False)
        # an inner failure the method catches is plain Python: nothing is undone
        assert store.put_recovering("x") == 1
        assert store.log == ["x"] and store.extra == "added during the call"
        store.put_many(["a"])
        live = store.state()
    finally:
        store.close()
    restored = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        assert restored.state() == live
    finally:
        restored.close()


def test_base_exceptions_roll_back(tmp_path):
    store = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        with pytest.raises(KeyboardInterrupt):
            store.interrupt()
        assert store.log == []
    finally:
        store.close()
    assert journaled(tmp_path) == []


def test_nested_proxy_call_rolls_back_to_its_own_start():
    proxy = None

    class Outer:
        def __init__(self):
            self.values = []

        @transactional
        def inner(self, fail):
            self.values.append("inner")
            if fail:
                raise ValueError("inner failed")

        @transactional
        def outer(self, fail_outer):
            self.values.append("outer")
            try:
                proxy.inner(True)
            except ValueError:
                pass
            # inner restored attributes as they were when it started
            self.values.append("after inner")
            if fail_outer:
                raise ValueError("outer failed")

    proxy = CoopyProxy(Outer(), [])
    proxy.outer(False)
    assert proxy.values == ["outer", "after inner"]
    with pytest.raises(ValueError, match="outer failed"):
        proxy.outer(True)
    assert proxy.values == ["outer", "after inner"]


@pytest.mark.parametrize("decorator", [readonly, unlocked])
def test_rejects_readonly_and_unlocked(decorator):
    class Domain:
        @decorator
        @transactional
        def first(self):
            pass

        @transactional
        @decorator
        def second(self):
            pass

    proxy = CoopyProxy(Domain(), [])
    for name in ("first", "second"):
        with pytest.raises(ConfigurationError, match="cannot be combined"):
            getattr(proxy, name)


def test_uncopyable_state_refuses_the_call():
    class Locked:
        def __init__(self):
            self.lock = threading.Lock()
            self.values = []

        @transactional
        def add(self, value):
            self.values.append(value)

    published = []

    class Subscriber:
        receive_before = receive = receive_exception = published.append

    proxy = CoopyProxy(Locked(), [Subscriber()])
    with pytest.raises(ConfigurationError, match="could not copy") as caught:
        proxy.add(1)
    assert isinstance(caught.value.__cause__, TypeError)
    assert proxy.values == [] and published == []


def fail_first_sync(monkeypatch):
    real_sync = os.fsync
    calls = []

    def fsync(fd):
        calls.append(fd)
        if len(calls) == 1:
            raise OSError("disk failure")
        real_sync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    return calls


def test_sync_persistence_failure_rolls_back_and_discards_record(tmp_path, monkeypatch):
    store = init_persistent_system(Store, basedir=str(tmp_path), durability="sync")
    store.put("a")
    before = store.state()
    journal = store.publisher.subscribers[0]
    size = os.path.getsize(journal.file.name)
    fail_first_sync(monkeypatch)
    with pytest.raises(PersistenceError, match="removed from the journal") as caught:
        store.put("b")
    assert caught.value.record_discarded is True
    assert str(caught.value.__cause__) == "disk failure"
    assert store.state() == before
    assert os.path.getsize(journal.file.name) == size
    with pytest.raises(PersistenceError):
        store.put("refused")
    assert store.state() == before
    store.close()
    monkeypatch.undo()

    restored = init_persistent_system(Store, basedir=str(tmp_path), durability="sync")
    try:
        assert restored.state() == before
    finally:
        restored.close()


def test_sync_persistence_failure_of_plain_call_is_unchanged(tmp_path, monkeypatch):
    store = init_persistent_system(Store, basedir=str(tmp_path), durability="sync")
    fail_first_sync(monkeypatch)
    with pytest.raises(PersistenceError, match="No rollback") as caught:
        store.put_plain("kept")
    assert caught.value.record_discarded is False
    assert store.log == ["kept"]
    store.close()
    monkeypatch.undo()
    restored = init_persistent_system(Store, basedir=str(tmp_path), durability="sync")
    try:
        assert restored.log == ["kept"]
    finally:
        restored.close()


def test_failure_after_the_record_is_complete_is_not_rolled_back(tmp_path):
    store = init_persistent_system(Store, basedir=str(tmp_path), durability="sync")
    journal = store.publisher.subscribers[0]
    journal.file.max_size = 1

    def fail_rotation(file_name):
        raise OSError("rotation failed")

    journal.file.rotate = fail_rotation
    with pytest.raises(PersistenceError, match="No rollback"):
        store.put("synced")
    # the record is on disk and will be replayed, so memory keeps it too
    assert store.log == ["synced"]
    store.close()
    restored = init_persistent_system(Store, basedir=str(tmp_path), durability="sync")
    try:
        assert restored.log == ["synced"]
    finally:
        restored.close()


def test_failed_calls_are_not_replicated():
    master = CoopyProxy(Store(), [])
    replica = CoopyProxy(Store(), [])
    master.put("a")
    master.start_primary(port=0)
    address = master.master.server.getsockname()
    try:
        assert replica.start_replica(*address).wait_until_synchronized(3)
        with pytest.raises(ValueError):
            master.put("b", fail=True)
        master.put("c")
        wait_for(lambda: replica.count == 2)
        assert replica.state() == master.state()
        assert replica.log == ["a", "c"]
        with pytest.raises(Exception, match="read-only"):
            replica.put("d")
    finally:
        replica.close()
        master.close()


class FlakyFile:
    """Leaves written bytes in the buffer: the first flush fails."""

    def __init__(self, file):
        self.file = file
        self.failed = False

    def flush(self):
        if not self.failed:
            self.failed = True
            raise OSError("flush failed")
        self.file.flush()

    def __getattr__(self, name):
        return getattr(self.file, name)


def test_buffered_bytes_of_a_discarded_record_are_cut_on_close(tmp_path):
    store = init_persistent_system(Store, basedir=str(tmp_path))
    store.put("a")
    before = store.state()
    journal = store.publisher.subscribers[0]
    name = journal.file.name
    size = os.path.getsize(name)
    journal.file.file = FlakyFile(journal.file.file)
    with pytest.raises(PersistenceError, match="removed from the journal"):
        store.put("b")
    assert store.state() == before
    store.close()
    assert os.path.getsize(name) == size
    restored = init_persistent_system(Store, basedir=str(tmp_path))
    try:
        assert restored.state() == before
    finally:
        restored.close()
