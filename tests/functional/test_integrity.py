"""Authenticate all restore input before allowing any pickle execution."""
import os
import pickle
from pathlib import Path
import subprocess
import sys

import pytest

from coopy import fileutils, restore, snapshot
from coopy.base import init_persistent_system
from coopy.integrity import HEADER, IDENTITY_FILE, MAGIC, TAG_SIZE, Integrity
from coopy.restore import RecoveryError
from .test_recovery_policy import Ledger

SECRET = b'test-only-secret-kept-outside-the-data-directory'


def signed(directory):
    proxy = init_persistent_system(Ledger, str(directory), secret=SECRET)
    proxy.add('first')
    proxy.add('second')
    journal = Path(proxy.publisher.subscribers[0].file.name)
    proxy.close()
    return journal


def rejects_without_unpickling(directory, monkeypatch, *, secret=SECRET):
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('Unpickler must not be constructed')

    monkeypatch.setattr(restore, 'Unpickler', forbidden)
    monkeypatch.setattr(snapshot, 'Unpickler', forbidden)
    with pytest.raises(RecoveryError, match='verification') as caught:
        init_persistent_system(Ledger, str(directory), secret=secret)
    report = caught.value.report
    assert report.stop.kind == 'verification'
    assert report.replayed == 0
    result = init_persistent_system(Ledger, str(directory), secret=secret, recovery='salvage')
    assert result.system is None
    assert result.report == report
    assert not calls
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}
    return report


@pytest.mark.parametrize('damage', ['byte', 'tag', 'tag_middle', 'header', 'length', 'truncate', 'append', 'unsigned', 'reorder'])
def test_journal_tampering_prevents_even_snapshot_unpickle(tmp_path, monkeypatch, damage):
    journal = signed(tmp_path)
    data = journal.read_bytes()
    boundary = len(MAGIC) + HEADER.size
    size, = HEADER.unpack(data[len(MAGIC):boundary])
    first_end = boundary + size + TAG_SIZE
    if damage == 'byte':
        data = data[:boundary + 5] + bytes([data[boundary + 5] ^ 1]) + data[boundary + 6:]
    elif damage == 'tag':
        data = data[:-TAG_SIZE]
    elif damage == 'tag_middle':
        data = data[:first_end - TAG_SIZE] + data[first_end:]
    elif damage == 'header':
        data = b'!' + data[1:]
    elif damage == 'length':
        data = MAGIC + HEADER.pack(2**64 - 1) + data[boundary:]
    elif damage == 'truncate':
        data = data[:-TAG_SIZE - 10]
    elif damage == 'append':
        data += b'x'
    elif damage == 'unsigned':
        data = pickle.dumps(Ledger())
    elif damage == 'reorder':
        data = data[first_end:] + data[:first_end]
    journal.write_bytes(data)
    report = rejects_without_unpickling(tmp_path, monkeypatch)
    assert report.stop.position.file == str(journal)
    if damage in ('tag', 'truncate', 'append'):
        assert report.stop.position.record >= 2
        assert report.stop.position.offset >= first_end


@pytest.mark.parametrize('damage', ['byte', 'tag', 'truncate', 'append', 'unsigned', 'swap'])
def test_snapshot_tampering(tmp_path, monkeypatch, damage):
    target = tmp_path / 'target'
    signed(target)
    checkpoint = next(target.glob('snapshot_*.dat'))
    data = checkpoint.read_bytes()
    if damage == 'byte':
        data = data[:-1] + bytes([data[-1] ^ 1])
    elif damage == 'tag':
        data = data[:-TAG_SIZE]
    elif damage == 'truncate':
        data = data[:4]
    elif damage == 'append':
        data += b'x'
    elif damage == 'unsigned':
        data = pickle.dumps(Ledger())
    elif damage == 'swap':
        other = tmp_path / 'other'
        signed(other)  # Same secret and filename, but a different system identity.
        data = next(other.glob('snapshot_*.dat')).read_bytes()
    checkpoint.write_bytes(data)
    report = rejects_without_unpickling(target, monkeypatch)
    assert report.stop.position.record == 0
    assert report.stop.position.file == str(checkpoint)


@pytest.mark.parametrize('damage', ['wrong_secret', 'missing_identity', 'identity_byte', 'missing_checkpoint', 'unsigned_directory'])
def test_identity_and_mode_fail_closed(tmp_path, monkeypatch, damage):
    if damage == 'unsigned_directory':
        p = init_persistent_system(Ledger, str(tmp_path))
        p.add('legacy')
        p.close()
    else:
        signed(tmp_path)
    if damage == 'missing_identity':
        (tmp_path / IDENTITY_FILE).unlink()
    elif damage == 'identity_byte':
        p = tmp_path / IDENTITY_FILE
        data = p.read_bytes()
        p.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    elif damage == 'missing_checkpoint':
        next(tmp_path.glob('snapshot_*.dat')).unlink()
    rejects_without_unpickling(tmp_path, monkeypatch,
                              secret=b'wrong' if damage == 'wrong_secret' else SECRET)


@pytest.mark.parametrize('secret', ['', b'', 1, bytearray(b'key')])
def test_invalid_secret_has_no_storage_effect(tmp_path, secret):
    with pytest.raises(ValueError, match='secret'):
        init_persistent_system(Ledger, str(tmp_path), secret=secret)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('durability', ['buffered', 'sync'])
def test_signed_restart_rotation_checkpoints_and_expected_exceptions(tmp_path, durability):
    proxy = init_persistent_system(Ledger, str(tmp_path), secret=SECRET, durability=durability)
    proxy.add('before')
    proxy.take_snapshot()
    proxy.publisher.subscribers[0].file.max_size = 1
    with pytest.raises(ValueError):
        proxy.fail('expected')
    proxy.add('after')
    proxy.close()
    # Obsolete files are outside recovery input, just as in unsigned storage.
    sorted(tmp_path.glob('snapshot_*.dat'))[0].write_bytes(b'obsolete')
    proxy = init_persistent_system(Ledger, str(tmp_path), secret=SECRET, durability=durability)
    assert proxy.values == ['before', 'expected', 'after']
    assert proxy.recovery_report.expected_failures == 1
    proxy.take_snapshot()
    proxy.add('reopened')
    proxy.close()
    proxy = init_persistent_system(Ledger, str(tmp_path), secret=SECRET)
    assert proxy.values == ['before', 'expected', 'after', 'reopened']
    proxy.close()
    assert all(SECRET not in p.read_bytes() for p in tmp_path.iterdir())


def test_unsigned_legacy_format_is_unchanged(tmp_path):
    proxy = init_persistent_system(Ledger, str(tmp_path))
    proxy.add('legacy')
    proxy.close()
    assert not (tmp_path / IDENTITY_FILE).exists()
    with next(tmp_path.glob('snapshot_*.dat')).open('rb') as f:
        assert isinstance(pickle.load(f), Ledger)
    with next(tmp_path.glob('transaction_*.log')).open('rb') as f:
        assert pickle.load(f).args == ('legacy',)
    proxy = init_persistent_system(Ledger, str(tmp_path))
    assert proxy.values == ['legacy']
    proxy.close()


def test_replay_uses_verified_bytes_despite_later_disk_change(tmp_path, monkeypatch):
    journal = signed(tmp_path)
    real = restore.Unpickler
    def replace_after_verification(file):
        journal.write_bytes(b'untrusted replacement')
        return real(file)
    monkeypatch.setattr(restore, 'Unpickler', replace_after_verification)
    result = init_persistent_system(Ledger, str(tmp_path), secret=SECRET, recovery='salvage')
    assert result.report.complete
    assert result.system.values == ['first', 'second']


def test_signed_sync_writes_whole_authenticated_record_before_ack(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, str(tmp_path), secret=SECRET, durability='sync')
    journal = proxy.publisher.subscribers[0]
    real = os.fsync
    calls = []
    def observe(fd):
        with open(journal.file.name, 'rb') as f:
            payload = journal.integrity.read(f, f.name)
        assert pickle.loads(payload).args == ('x' * 200000,)
        calls.append(fd)
        real(fd)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', observe)
        proxy.add('x' * 200000)
        assert len(calls) == 1
    proxy.close()


def test_fresh_process_signed_restart(tmp_path):
    signed(tmp_path)
    script = '''
from coopy.base import init_persistent_system
from tests.functional.test_recovery_policy import Ledger
p = init_persistent_system(Ledger, '.', secret=%r)
assert p.values == ['first', 'second']
p.take_snapshot()
p.add('third')
p.close()
''' % SECRET
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    subprocess.run([sys.executable, '-c', script], cwd=tmp_path, env=env, check=True, timeout=20)
    proxy = init_persistent_system(Ledger, str(tmp_path), secret=SECRET)
    assert proxy.values == ['first', 'second', 'third']
    proxy.close()


@pytest.mark.parametrize('fault', ['short', 'partial', 'fsync'])
def test_signed_persistence_failures_are_observable(tmp_path, monkeypatch, fault):
    from coopy.journal import PersistenceError
    from .test_durability import FaultFile
    proxy = init_persistent_system(Ledger, str(tmp_path), secret=SECRET, durability='sync')
    journal = proxy.publisher.subscribers[0]
    original = journal.file.file
    with monkeypatch.context() as patch:
        if fault == 'fsync':
            def fail(fd):
                raise OSError('injected sync failure')
            patch.setattr(os, 'fsync', fail)
        else:
            journal.file.file = FaultFile(original, fault)
        with pytest.raises(PersistenceError):
            proxy.add('possibly persisted')
        with pytest.raises(PersistenceError, match='disabled'):
            proxy.add('refused')
    journal.file.file = original
    proxy.close()
    if fault != 'fsync':
        rejects_without_unpickling(tmp_path, monkeypatch)


def test_signed_journal_cannot_move_between_files(tmp_path, monkeypatch):
    journal = signed(tmp_path)
    moved = tmp_path / 'transaction_000000000000999.log'
    journal.rename(moved)
    report = rejects_without_unpickling(tmp_path, monkeypatch)
    assert report.stop.position.file == str(moved)


def test_low_level_signed_snapshot_recovery(tmp_path):
    signed(tmp_path)
    integrity = Integrity.open(str(tmp_path), SECRET)
    manager = snapshot.SnapshotManager(str(tmp_path), integrity=integrity)
    assert isinstance(manager.recover_snapshot(), Ledger)
