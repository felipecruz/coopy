"""Fork tests run in a fresh single-threaded interpreter on supported POSIX hosts."""
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from coopy.base import control, init_persistent_system
from coopy.snapshot import fork_supported, SnapshotJob, SnapshotManager
from .test_recovery_policy import Ledger


@pytest.mark.parametrize('safe', [False, True])
def test_fork_eligibility_requires_single_main_thread(monkeypatch, safe):
    monkeypatch.setattr('coopy.snapshot.sys.platform', 'linux')
    monkeypatch.setattr(threading, 'active_count', lambda: 2)
    assert not fork_supported(safe)
    monkeypatch.setattr(threading, 'active_count', lambda: 1)
    assert fork_supported(safe) == safe
    monkeypatch.setattr(threading, 'current_thread', lambda: object())
    assert not fork_supported(True)


@pytest.mark.parametrize('restriction', ['macos', 'threads', 'not_opted_in', 'replication'])
def test_fork_falls_back_without_calling_fork(tmp_path, monkeypatch, restriction):
    proxy = init_persistent_system(Ledger, tmp_path)
    proxy.add('before')
    monkeypatch.setattr(os, 'fork', lambda: pytest.fail('unsafe fork attempted'))
    monkeypatch.setattr('coopy.snapshot.sys.platform', 'darwin' if restriction == 'macos' else 'linux')
    if restriction == 'threads':
        monkeypatch.setattr(threading, 'active_count', lambda: 2)
    if restriction == 'replication':
        proxy.master = object()
    with pytest.warns(RuntimeWarning, match='blocking snapshot'):
        assert control(proxy).take_snapshot(mode='fork', fork_safe=restriction != 'not_opted_in') is None
    control(proxy).close()
    restored = init_persistent_system(Ledger, tmp_path)
    assert restored.values == ['before']
    control(restored).close()


def test_fork_creation_failure_preserves_replay(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, tmp_path)
    proxy.add('before')
    monkeypatch.setattr('coopy.base.fork_supported', lambda safe: True)
    def fail():
        raise OSError('fork failed')
    monkeypatch.setattr(os, 'fork', fail)
    with pytest.raises(OSError, match='fork failed'):
        control(proxy).take_snapshot(mode='fork', fork_safe=True)
    assert not list(tmp_path.glob('.coopy-snapshot-*'))
    proxy.add('after')
    control(proxy).close()
    restored = init_persistent_system(Ledger, tmp_path)
    assert restored.values == ['before', 'after']
    control(restored).close()


@pytest.mark.parametrize('boundary', ['fsync', 'rename', 'directory'])
def test_parent_publication_failure_cleans_hidden_snapshot(tmp_path, monkeypatch, boundary):
    temporary = tmp_path / '.coopy-snapshot-test'
    temporary.write_bytes(b'complete serialization')
    destination = tmp_path / 'snapshot_000000000000002.dat'
    job = SnapshotJob(1234, str(temporary), str(destination), SnapshotManager(tmp_path, durability='sync'))
    monkeypatch.setattr(os, 'waitpid', lambda pid, flags: (pid, 0))
    monkeypatch.setattr(os, 'kill', lambda *args: pytest.fail('already reaped child killed'))
    def fail(*args):
        raise OSError('injected parent failure')
    if boundary == 'fsync':
        monkeypatch.setattr(os, 'fsync', fail)
    elif boundary == 'rename':
        monkeypatch.setattr(os, 'replace', fail)
    else:
        monkeypatch.setattr('coopy.snapshot.fu.sync_directory', fail)
    for _ in range(2):
        with pytest.raises(OSError, match='injected parent failure'):
            job.wait()
    assert job.done
    assert not temporary.exists()
    assert destination.exists() == (boundary == 'directory')


SCRIPT = r'''
import os, pickle, sys, time
from unittest.mock import patch
from coopy.base import init_persistent_system, control
from coopy.error import LifecycleError, PersistenceError
from coopy.snapshot import SnapshotManager

# Test-only access to the POSIX mechanism in a pristine macOS CLI subprocess.
# This is not a supported application configuration and does not enable fork
# in the public API. No framework clients, application threads, or callbacks
# beyond the deliberately controlled serializer below exist in this process.
if sys.platform == 'darwin' and os.environ.get('COOPY_TEST_FORK_INTERNAL') == '1':
    import coopy.base
    coopy.base.fork_supported = lambda safe: safe

class Ledger:
    def __init__(self):
        self.values = []
        self.behavior = 'ok'
    def add(self, value):
        self.values.append(value)
    def __getstate__(self):
        if self.behavior == 'slow':
            time.sleep(0.3)
        if self.behavior == 'error':
            raise ValueError('cannot serialize')
        if self.behavior == 'timeout':
            time.sleep(20)
        return self.__dict__

directory, scenario, codec, signing = sys.argv[1:]
codec = None if codec == 'none' else codec
secret = b'key' if signing == 'signed' else None
p = init_persistent_system(Ledger, directory, durability='sync',
                           snapshot_compression=codec, secret=secret)
p.add('before')
p.obj.behavior = 'error' if scenario == 'child_error' else 'timeout' if scenario == 'timeout' else 'slow'
job = control(p).take_snapshot(mode='fork', fork_safe=True)
assert job is not None
# No second snapshot can overtake the reserved checkpoint while it is hidden.
try:
    control(p).take_snapshot()
except LifecycleError:
    pass
else:
    raise AssertionError('overlapping snapshot allowed')
p.add('after')
if scenario == 'publication':
    with patch('coopy.snapshot.os.replace', side_effect=OSError('rename failed')):
        try:
            job.wait()
        except OSError:
            pass
        else:
            raise AssertionError('publication did not fail')
elif scenario in ('child_error', 'timeout'):
    try:
        job.wait(timeout=0.05 if scenario == 'timeout' else 5)
    except (PersistenceError, TimeoutError):
        pass
    else:
        raise AssertionError('child failure did not propagate')
elif scenario == 'close':
    control(p).close()
else:
    job.wait()
    job.wait()  # idempotent
assert job.done
try:
    os.waitpid(job.pid, os.WNOHANG)
except ChildProcessError:
    pass
else:
    raise AssertionError('child not reaped')
try:
    control(p).close()
except (OSError, PersistenceError, TimeoutError):
    assert scenario in ('publication', 'child_error', 'timeout')
r = init_persistent_system(Ledger, directory, secret=secret)
assert r.values == ['before', 'after'], r.values
assert r.recovery_report.replayed == (2 if scenario in ('publication', 'child_error', 'timeout') else 1)
control(r).close()
'''


@pytest.mark.skipif(os.name != 'posix' or (sys.platform == 'darwin' and os.environ.get('COOPY_TEST_FORK_INTERNAL') != '1'),
                    reason='fork snapshots require supported POSIX host')
@pytest.mark.parametrize('scenario', ['success', 'child_error', 'timeout', 'publication', 'close'])
@pytest.mark.parametrize('codec', ['none', 'zstd', 'lz4'])
@pytest.mark.parametrize('signing', ['signed', 'unsigned'])
def test_fork_copy_on_write_and_failure_recovery(tmp_path, scenario, codec, signing):
    if codec != 'none':
        pytest.importorskip('zstandard' if codec == 'zstd' else 'lz4.frame')
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    subprocess.run([sys.executable, '-c', SCRIPT, str(tmp_path), scenario, codec, signing],
                   env=env, check=True, timeout=15)
    assert not list(tmp_path.glob('.coopy-snapshot-*'))
