"""Checkpoint boundaries, failure publication, and legacy stream compatibility."""
import os
import pickle
import subprocess
import sys
import threading
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
            if failure == 'write':
                self.file.write(b'partial pickle')
                raise OSError('disk full')
            raise pickle.PicklingError('not serializable')

    journal = ledger.publisher.subscribers[0]
    if failure in ('serialization', 'write'):
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


def test_interruption_before_publication(tmp_path):
    script = '''
import os, sys
from unittest.mock import patch
from tests.functional.test_snapshot_recovery import open_ledger
ledger = open_ledger(sys.argv[1])
ledger.add('survives interruption')
with patch('coopy.snapshot.os.replace', side_effect=lambda *args: os._exit(17)):
    ledger.take_snapshot()
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], timeout=10)
    assert result.returncode == 17
    assert list(tmp_path.glob('.coopy-snapshot-*'))
    ledger = open_ledger(tmp_path)
    assert ledger.entries == ['survives interruption']
    ledger.add('after restart')
    ledger.take_snapshot()
    ledger.close()
    ledger = open_ledger(tmp_path)
    assert ledger.entries == ['survives interruption', 'after restart']
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
