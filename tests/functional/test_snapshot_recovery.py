"""Checkpoint boundaries, failure publication, and legacy stream compatibility."""
import os
import pickle
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch

import pytest

from coopy import fileutils
from coopy.base import init_persistent_system
from coopy.foundation import Action
from coopy.snapshot import SnapshotManager


class Ledger:
    def __init__(self):
        self.entries = []

    def add(self, value):
        self.entries.append(value)


def open_ledger(directory):
    return init_persistent_system(Ledger, basedir=str(directory))


def test_repeated_checkpoints_and_reopen(tmp_path):
    ledger = open_ledger(tmp_path)
    expected = []
    for i in range(3):
        ledger.add(i)
        expected.append(i)
        ledger.take_snapshot()
        ledger.add(i + 10)
        expected.append(i + 10)
    ledger.close()
    for i in range(3):
        ledger = open_ledger(tmp_path)
        assert ledger.entries == expected
        ledger.add(i + 20)
        expected.append(i + 20)
        ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == expected
    ledger.close()


@pytest.mark.parametrize('timed', [False, True], ids=['manual', 'timer'])
@pytest.mark.parametrize('boundary', ['rotation', 'publication'])
def test_checkpoint_excludes_concurrent_write_until_publication(tmp_path, timed, boundary):
    ledger = open_ledger(tmp_path)
    ledger.add('A')
    journal = ledger.publisher.subscribers[0]
    old_journal = journal.file.name
    old_snapshot = fileutils.last_snapshot_file(str(tmp_path))
    reached = threading.Event()
    proceed = threading.Event()
    writer_started = threading.Event()
    if boundary == 'rotation':
        target, attribute = journal, 'checkpoint'
    else:
        target, attribute = os, 'replace'
    original = getattr(target, attribute)

    def pause(*args):
        reached.set()
        assert proceed.wait(5), 'checkpoint was not released'
        return original(*args)

    def write():
        writer_started.set()
        ledger.add('B')

    try:
        with patch.object(target, attribute, pause), ThreadPoolExecutor(2) as pool:
            snapshot = None
            if timed:
                ledger.start_snapshot_manager(0.01)
            else:
                snapshot = pool.submit(ledger.take_snapshot)
            try:
                assert reached.wait(5)
                # Test from another thread: RLock reentrancy must not disguise
                # a checkpoint that released the domain lock too early.
                acquired = ledger.lock.acquire(blocking=False)
                if acquired:
                    ledger.lock.release()
                assert not acquired
                assert fileutils.last_snapshot_file(str(tmp_path)) == old_snapshot
                if boundary == 'publication':
                    assert journal.file.name != old_journal
                writer = pool.submit(write)
                assert writer_started.wait(5)
                assert not writer.done()
            finally:
                if timed:
                    # Prevent another timer tick from checkpointing B.
                    ledger.snapshot_timer.finished.set()
                proceed.set()
            if snapshot:
                snapshot.result(timeout=5)
            else:
                ledger.snapshot_timer.stop()
            writer.result(timeout=5)

        snapshot_name = fileutils.last_snapshot_file(str(tmp_path))
        assert fileutils.get_number(os.path.basename(old_journal)) < fileutils.get_number(snapshot_name)
        assert fileutils.get_number(snapshot_name) < fileutils.get_number(os.path.basename(journal.file.name))
        assert SnapshotManager(str(tmp_path)).recover_snapshot().entries == ['A']
    finally:
        ledger.close()

    ledger = open_ledger(tmp_path)
    try:
        assert ledger.entries == ['A', 'B']
        ledger.add('C')
        ledger.take_snapshot()
        ledger.add('D')
    finally:
        ledger.close()
    ledger = open_ledger(tmp_path)
    try:
        assert ledger.entries == ['A', 'B', 'C', 'D']
    finally:
        ledger.close()


def test_timer_checkpoint_and_retry_after_failure(tmp_path):
    ledger = open_ledger(tmp_path)
    ledger.add('before')
    completed = threading.Event()
    calls = []
    take_snapshot = ledger.snapshot_manager.take_snapshot

    def snapshot(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise OSError('transient write failure')
        take_snapshot(*args, **kwargs)
        completed.set()

    with patch.object(ledger.snapshot_manager, 'take_snapshot', snapshot):
        ledger.start_snapshot_manager(0.01)
        try:
            assert completed.wait(3)
            ledger.snapshot_timer.stop()
            ledger.add('after')
        finally:
            ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == ['before', 'after']
    ledger.close()


@pytest.mark.parametrize('failure', ['serialization', 'write', 'fsync', 'rotation', 'publication'])
def test_failed_snapshot_retains_checkpoint_and_journals(tmp_path, failure):
    ledger = open_ledger(tmp_path)
    ledger.add('before')
    previous = fileutils.last_snapshot_file(str(tmp_path))

    class FailingPickler:
        def __init__(self, file, protocol):
            self.file = file

        def dump(self, obj):
            self.file.write(b'partial pickle')
            raise OSError('disk full')

    journal = ledger.publisher.subscribers[0]
    if failure == 'serialization':
        injection = patch.object(Ledger, '__getstate__', create=True,
                                 side_effect=pickle.PicklingError('not serializable'))
    elif failure == 'write':
        injection = patch('coopy.snapshot.Pickler', FailingPickler)
    elif failure == 'fsync':
        injection = patch('coopy.snapshot.os.fsync', side_effect=OSError('sync failed'))
    elif failure == 'rotation':
        injection = patch.object(journal.file, 'rotate', side_effect=OSError('open failed'))
    else:
        injection = patch('coopy.snapshot.os.replace', side_effect=OSError('rename failed'))
    with injection, pytest.raises((OSError, pickle.PicklingError)):
        ledger.take_snapshot()
    assert fileutils.last_snapshot_file(str(tmp_path)) == previous
    assert SnapshotManager(str(tmp_path)).recover_snapshot().entries == []
    assert not list(tmp_path.glob('.coopy-snapshot-*'))
    ledger.add('after')
    ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == ['before', 'after']
    ledger.take_snapshot()
    ledger.add('after successful retry')
    ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == ['before', 'after', 'after successful retry']
    ledger.close()


@pytest.mark.parametrize('failure', ['write', 'flush', 'close'])
@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_snapshot_file_failure_preserves_original_error_and_recovery(
        tmp_path, failure, cleanup_fails, caplog):
    ledger = open_ledger(tmp_path)
    ledger.add('checkpoint')
    ledger.take_snapshot()
    previous = fileutils.last_snapshot_file(str(tmp_path))
    previous_bytes = (tmp_path / previous).read_bytes()
    ledger.add('journal tail')
    journals = {name: (tmp_path / name).read_bytes()
                for name in fileutils.list_log_files(str(tmp_path))}
    original_factory = tempfile.NamedTemporaryFile
    original_unlink = os.unlink
    error = OSError('injected snapshot ' + failure + ' failure')

    class FailingFile:
        # Use the real Pickler and real temporary file, failing at file I/O.
        def __init__(self, *args, **kwargs):
            self.file = original_factory(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.file, name)

        def __enter__(self):
            return self

        def write(self, data):
            if failure == 'write':
                self.file.write(data[:len(data) // 2])
                self.file.flush()
                raise error
            return self.file.write(data)

        def flush(self):
            if failure == 'flush':
                raise error
            return self.file.flush()

        def __exit__(self, *args):
            self.file.close()
            if failure == 'close':
                raise error

    def unlink(filename):
        if cleanup_fails and os.path.basename(filename).startswith('.coopy-snapshot-'):
            raise PermissionError('injected cleanup failure')
        return original_unlink(filename)

    try:
        with patch('coopy.snapshot.tempfile.NamedTemporaryFile', FailingFile), \
                patch('coopy.snapshot.os.unlink', unlink), \
                pytest.raises(OSError) as caught:
            ledger.take_snapshot()
        assert caught.value is error
        assert fileutils.last_snapshot_file(str(tmp_path)) == previous
        assert (tmp_path / previous).read_bytes() == previous_bytes
        assert SnapshotManager(str(tmp_path)).recover_snapshot().entries == ['checkpoint']
        assert {name: (tmp_path / name).read_bytes()
                for name in fileutils.list_log_files(str(tmp_path))} == journals
        assert bool(list(tmp_path.glob('.coopy-snapshot-*'))) == cleanup_fails
        if cleanup_fails:
            assert 'Unable to remove incomplete snapshot' in caplog.text
        ledger.add('after failure')
    finally:
        ledger.close()

    ledger = open_ledger(tmp_path)
    try:
        assert ledger.entries == ['checkpoint', 'journal tail', 'after failure']
        ledger.take_snapshot()
        ledger.add('after retry')
    finally:
        ledger.close()
    ledger = open_ledger(tmp_path)
    try:
        assert ledger.entries == ['checkpoint', 'journal tail', 'after failure', 'after retry']
    finally:
        ledger.close()


@pytest.mark.parametrize('boundary', ['write', 'rotation', 'publication'])
def test_interruption_before_publication(tmp_path, boundary):
    ledger = open_ledger(tmp_path)
    ledger.add('checkpoint')
    ledger.take_snapshot()
    ledger.add('previous journal')
    ledger.close()
    previous = fileutils.last_snapshot_file(str(tmp_path))
    previous_bytes = (tmp_path / previous).read_bytes()
    journals = {name: (tmp_path / name).read_bytes()
                for name in fileutils.list_log_files(str(tmp_path))}
    script = '''
import os, sys, tempfile
from unittest.mock import patch
from tests.functional.test_snapshot_recovery import open_ledger
ledger = open_ledger(sys.argv[1])
ledger.add('survives interruption')
boundary = sys.argv[2]
original_factory = tempfile.NamedTemporaryFile
def interrupted_file(*args, **kwargs):
    file = original_factory(*args, **kwargs)
    def write(data):
        file.file.write(data[:len(data) // 2])
        file.file.flush()
        os._exit(17)
    file.write = write
    return file
if boundary == 'write':
    injection = patch('coopy.snapshot.tempfile.NamedTemporaryFile', interrupted_file)
elif boundary == 'rotation':
    injection = patch.object(ledger.publisher.subscribers[0], 'checkpoint',
                             side_effect=lambda *args: os._exit(17))
else:
    injection = patch('coopy.snapshot.os.replace', side_effect=lambda *args: os._exit(17))
with injection:
    ledger.take_snapshot()
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), boundary], timeout=10)
    assert result.returncode == 17
    assert list(tmp_path.glob('.coopy-snapshot-*'))
    assert fileutils.last_snapshot_file(str(tmp_path)) == previous
    assert (tmp_path / previous).read_bytes() == previous_bytes
    assert SnapshotManager(str(tmp_path)).recover_snapshot().entries == ['checkpoint']
    assert all((tmp_path / name).read_bytes() == data for name, data in journals.items())
    ledger = open_ledger(tmp_path)
    assert ledger.entries == ['checkpoint', 'previous journal', 'survives interruption']
    ledger.add('after restart')
    ledger.take_snapshot()
    ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == ['checkpoint', 'previous journal', 'survives interruption', 'after restart']
    ledger.close()


def test_rotation_keeps_large_records_and_shared_references(tmp_path):
    ledger = open_ledger(tmp_path)
    ledger.take_snapshot()
    journal = ledger.publisher.subscribers[0]
    journal.file.max_size = 100
    shared = ['x' * 200000]
    # Large pickle records require multiple writes. Each record also has an
    # alias that must survive both memo reset and independent-file replay.
    for _ in range(3):
        ledger.add([shared, shared])
    ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == [[shared, shared]] * 3
    assert all(entry[0] is entry[1] for entry in ledger.entries)
    ledger.close()


def test_legacy_numbered_pickle_stream_is_preserved(tmp_path):
    snapshot = tmp_path / 'snapshot_000000000000004.dat'
    snapshot.write_bytes(pickle.dumps(Ledger(), protocol=2))
    log = tmp_path / 'transaction_000000000000005.log'
    shared = ['legacy']
    with log.open('wb') as file:
        pickler = pickle.Pickler(file, protocol=2)
        for _ in range(2):
            pickler.dump(Action(1, 'add', datetime(2020, 1, 1), (shared,), {}))
    original = log.read_bytes()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == [shared, shared]
    assert ledger.entries[0] is ledger.entries[1]
    ledger.add('new stream')
    ledger.close()
    assert log.read_bytes() == original
    ledger = open_ledger(tmp_path)
    assert ledger.entries == [shared, shared, 'new stream']
    ledger.take_snapshot()
    ledger.add('new checkpoint')
    ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == [shared, shared, 'new stream', 'new checkpoint']
    ledger.close()


@pytest.mark.parametrize('old_log_number', [3, 4])
def test_legacy_checkpoint_selection_does_not_replay_earlier_or_equal_logs(tmp_path, old_log_number):
    saved = Ledger()
    saved.add('A')
    snapshot = tmp_path / 'snapshot_000000000000004.dat'
    snapshot.write_bytes(pickle.dumps(saved, protocol=2))
    old_log = tmp_path / ('transaction_%015d.log' % old_log_number)
    with old_log.open('wb') as file:
        pickler = pickle.Pickler(file, protocol=2)
        # Old writers could append after a checkpoint to a lower-numbered
        # stream. There is no offset identifying that tail: preserve the
        # established selection rule instead of guessing and duplicating A.
        for value in ['A', 'ambiguous old tail']:
            pickler.dump(Action(1, 'add', datetime(2020, 1, 1), (value,), {}))

    expected = ['A']
    for number in [5, 6]:
        shared = ['legacy', number]
        log = tmp_path / ('transaction_%015d.log' % number)
        with log.open('wb') as file:
            pickler = pickle.Pickler(file, protocol=2)
            for _ in range(2):
                pickler.dump(Action(1, 'add', datetime(2020, 1, 1), (shared,), {}))
                expected.append(shared)
    originals = {file: file.read_bytes() for file in tmp_path.iterdir()}

    ledger = open_ledger(tmp_path)
    try:
        assert ledger.entries == expected
        assert ledger.entries[1] is ledger.entries[2]
        assert ledger.entries[3] is ledger.entries[4]
        assert ledger.entries[1] is not ledger.entries[3]
        ledger.add('B')
        ledger.take_snapshot()
        ledger.add('C')
    finally:
        ledger.close()
    assert all(file.read_bytes() == data for file, data in originals.items())
    ledger = open_ledger(tmp_path)
    try:
        assert ledger.entries == expected + ['B', 'C']
    finally:
        ledger.close()
