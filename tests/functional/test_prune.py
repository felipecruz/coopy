"""F29: prune old checkpoints and the journals only they need."""

import os
import threading
import time
from datetime import timedelta

import pytest

import coopy
from coopy import fileutils
from coopy.error import ConfigurationError, LifecycleError, LockError
from coopy.restore import recover

from .test_locking import Counter, start_holder
from .test_serialization import Tasks

SECRET = b"test-only-prune-secret"


def files(directory):
    snapshots = fileutils.list_snapshot_files(directory) or []
    journals = fileutils.list_log_files(directory) or []
    return snapshots, journals


def build(directory, checkpoints=5, **options):
    system = coopy.open(Tasks, directory, **options)
    for index in range(checkpoints):
        system.add("before", index)
        coopy.control(system).take_snapshot()
        system.add("after", index)
    return system


@pytest.mark.parametrize("secret", [None, SECRET])
def test_prune_keeps_newest_checkpoints_and_needed_journals(tmp_path, secret):
    system = build(tmp_path, secret=secret)
    expected = system.items[:]
    snapshots, journals = files(tmp_path)
    assert len(snapshots) == 6

    report = coopy.control(system).prune(keep=2)

    assert report.snapshots == snapshots[:-2]
    assert report.kept_snapshots == snapshots[-2:]
    oldest_kept = fileutils.get_number(snapshots[-2])
    assert report.journals == [j for j in journals if fileutils.get_number(j) < oldest_kept]
    assert files(tmp_path) == (snapshots[-2:], [j for j in journals if j not in report.journals])
    # Still writable after pruning, and recovery matches live state.
    system.add("later", 9)
    expected.append(("later", 9))
    coopy.control(system).close()
    with coopy.open(Tasks, tmp_path, secret=secret) as reopened:
        assert reopened.items == expected


def test_kept_older_checkpoint_still_replays_to_current_state(tmp_path):
    system = build(tmp_path)
    expected = system.items[:]
    coopy.control(system).prune(keep=3)
    coopy.control(system).close()
    snapshots, _ = files(tmp_path)
    # Hide the two newest checkpoints: the oldest kept one plus its journals
    # must still reproduce the current state.
    for name in snapshots[1:]:
        os.rename(tmp_path / name, tmp_path / ("hidden-" + name))
    with coopy.open(Tasks, tmp_path) as reopened:
        assert reopened.items == expected


def test_nothing_to_prune(tmp_path):
    with build(tmp_path, checkpoints=1) as system:
        before = files(tmp_path)
        report = coopy.control(system).prune(keep=2)
        assert report.removed == [] and files(tmp_path) == before
        report = coopy.control(system).prune(keep=2, keep_for=timedelta(0))
        assert report.removed == []


def test_keep_for_retains_recent_checkpoints(tmp_path):
    with build(tmp_path) as system:
        snapshots, _ = files(tmp_path)
        old = time.time() - 3 * 86400
        for name in snapshots[:2]:
            os.utime(tmp_path / name, (old, old))

        report = coopy.control(system).prune(keep=1, keep_for=timedelta(days=1))

        assert report.snapshots == snapshots[:2]
        assert files(tmp_path)[0] == snapshots[2:]
        assert coopy.control(system).prune(keep=1, keep_for=timedelta(days=1)).removed == []
        assert coopy.control(system).prune(keep=1).snapshots == snapshots[2:-1]


@pytest.mark.parametrize(
    "options",
    [
        {"keep": 0},
        {"keep": True},
        {"keep": 1.0},
        {"keep": 1, "keep_for": 5},
        {"keep": 1, "keep_for": timedelta(-1)},
    ],
)
def test_invalid_arguments(tmp_path, options):
    with coopy.open(Tasks, tmp_path) as system:
        with pytest.raises(ConfigurationError):
            coopy.control(system).prune(**options)
    with pytest.raises(ConfigurationError):
        coopy.prune(tmp_path, **options)


def test_closed_system_refuses_prune(tmp_path):
    system = coopy.open(Tasks, tmp_path)
    coopy.control(system).close()
    with pytest.raises(LifecycleError):
        coopy.control(system).prune(keep=1)


def test_signed_directory_stays_verifiable(tmp_path):
    expected = build(tmp_path, secret=SECRET)
    expected_items = expected.items[:]
    coopy.control(expected).close()

    report = coopy.prune(tmp_path, keep=1)

    assert len(report.snapshots) == 5
    root = Tasks()
    root._clock = None
    result = recover(root, tmp_path, mode="strict", secret=SECRET)
    assert result.report.complete and result.system.items == expected_items


def test_closed_directory_prune_honors_lock(tmp_path):
    coopy.control(build(tmp_path)).close()
    holder = start_holder(tmp_path / "held")
    try:
        with pytest.raises(LockError):
            coopy.prune(tmp_path / "held", keep=1)
    finally:
        holder.stdin.close()
        holder.wait(timeout=10)
    with coopy.open(Tasks, tmp_path) as system:
        with pytest.raises(LockError):
            coopy.prune(tmp_path, keep=1)
        expected = system.items[:]
    assert len(coopy.prune(tmp_path, keep=1).snapshots) == 5
    with coopy.open(Tasks, tmp_path) as reopened:
        assert reopened.items == expected
    with pytest.raises(ConfigurationError):
        coopy.prune(tmp_path / "missing", keep=1)


@pytest.mark.parametrize("durability", ["buffered", "sync"])
def test_prune_during_concurrent_writes_and_snapshots(tmp_path, durability):
    system = coopy.open(Counter, tmp_path, durability=durability)
    control = coopy.control(system)
    stop = threading.Event()
    errors = []

    def guarded(work):
        def run():
            try:
                while not stop.is_set():
                    work()
            except BaseException as error:  # pragma: no cover - reported below
                errors.append(error)

        return threading.Thread(target=run)

    threads = [
        guarded(system.increment),
        guarded(system.increment),
        guarded(control.take_snapshot),
        guarded(lambda: control.prune(keep=2)),
    ]
    for thread in threads:
        thread.start()
    time.sleep(0.5)
    stop.set()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors
    live = system.read()
    assert live > 0
    control.close()
    with coopy.open(Counter, tmp_path) as reopened:
        assert reopened.read() == live
        assert len(coopy.control(reopened).prune(keep=1).kept_snapshots) == 1
    with coopy.open(Counter, tmp_path) as reopened:
        assert reopened.read() == live
