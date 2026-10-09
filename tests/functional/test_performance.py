"""Group acknowledgment, checkpoint boundaries, and compressed recovery."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import os
import threading

import pytest

from coopy.base import control, init_persistent_system
from coopy import fileutils
from coopy.error import ConfigurationError, PersistenceError
from coopy.restore import RecoveryError
from coopy.serialization import JsonSerializer, TypeRegistry
from .test_recovery_policy import Ledger


@pytest.mark.parametrize('secret', [None, b'key'])
def test_concurrent_batches_and_checkpoints_replay_in_order(tmp_path, secret):
    proxy = init_persistent_system(Ledger, tmp_path, durability='sync', secret=secret, group_commit_delay=0.001)
    proxy.publisher.subscribers[0].file.max_size = 2048
    barrier = threading.Barrier(5)
    def write(worker):
        barrier.wait()
        for i in range(50):
            proxy.add((worker, i))
    def checkpoints():
        barrier.wait()
        for _ in range(15):
            control(proxy).take_snapshot()
    with ThreadPoolExecutor(5) as pool:
        futures = [pool.submit(write, worker) for worker in range(4)]
        futures.append(pool.submit(checkpoints))
        for future in futures:
            future.result(timeout=15)
    expected = list(proxy.values)
    assert len(expected) == len(set(expected)) == 200
    control(proxy).close()
    restored = init_persistent_system(Ledger, tmp_path, secret=secret)
    assert restored.values == expected
    control(restored).close()


def test_zero_delay_preserves_immediate_sync(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, tmp_path, durability='sync', group_commit_delay=0)
    journal = proxy.publisher.subscribers[0]
    assert journal.condition is None
    calls = []
    real_sync = os.fsync
    with monkeypatch.context() as patch:
        patch.setattr(os, 'fsync', lambda fd: (calls.append(fd), real_sync(fd)))
        proxy.add('one')
        proxy.add('two')
        assert len(calls) == 2
    control(proxy).close()


def test_domain_exception_waits_for_group_sync(tmp_path, monkeypatch):
    proxy = init_persistent_system(Ledger, tmp_path, durability='sync', group_commit_delay=0.2)
    journal = proxy.publisher.subscribers[0]
    receive = journal.receive
    appended = threading.Event()
    synced = threading.Event()
    flush = journal.file.flush
    def append(action):
        receive(action)
        if journal.pending == 2:
            appended.set()
    def sync():
        assert appended.is_set()
        flush()
        synced.set()
    monkeypatch.setattr(journal, 'receive', append)
    monkeypatch.setattr(journal.file, 'flush', sync)
    with ThreadPoolExecutor(2) as pool:
        failed = pool.submit(proxy.fail, 'failed')
        succeeded = pool.submit(proxy.add, 'ok')
        with pytest.raises(ValueError, match='expected domain failure'):
            failed.result(timeout=5)
        assert synced.is_set()
        succeeded.result(timeout=5)
    expected = list(proxy.values)
    control(proxy).close()
    restored = init_persistent_system(Ledger, tmp_path)
    assert restored.values == expected
    assert restored.recovery_report.expected_failures == 1
    control(restored).close()


@pytest.mark.parametrize('fault', [None, 'fsync', 'rotation', 'append'])
def test_group_acknowledgment_and_failure(tmp_path, monkeypatch, fault):
    proxy = init_persistent_system(Ledger, tmp_path, durability='sync', group_commit_delay=0.2)
    journal = proxy.publisher.subscribers[0]
    appended = threading.Event()
    syncing = threading.Event()
    release = threading.Event()
    calls = []
    receive = journal.receive
    flush = journal.file.flush

    def append(action):
        if fault == 'append' and len(proxy.values) == 8:
            journal._failed(OSError('injected append failure'))
        receive(action)
        if journal.pending == 8:
            appended.set()

    def sync():
        calls.append(journal.pending)
        syncing.set()
        assert release.wait(5)
        if fault == 'fsync':
            raise OSError('injected batch fsync failure')
        flush()

    with monkeypatch.context() as patch, ThreadPoolExecutor(8) as pool:
        patch.setattr(journal, 'receive', append)
        patch.setattr(journal.file, 'flush', sync)
        if fault == 'rotation':
            patch.setattr(journal.file, 'rotate_if_needed',
                          lambda: (_ for _ in ()).throw(OSError('injected rotation failure')))
        futures = [pool.submit(proxy.add, i) for i in range(8)]
        try:
            if fault != 'append':
                assert appended.wait(5)
                assert syncing.wait(5)
                assert not any(f.done() for f in futures)
        finally:
            release.set()
        for future in futures:
            if fault:
                with pytest.raises(PersistenceError):
                    future.result(timeout=5)
            else:
                future.result(timeout=5)
        if fault:
            with pytest.raises(PersistenceError):
                proxy.add('refused')
            with pytest.raises(PersistenceError):
                control(proxy).take_snapshot()
        else:
            assert calls == [8]
            assert journal.synchronized == 8
    expected = list(proxy.values)
    control(proxy).close()
    if fault != 'append':
        restored = init_persistent_system(Ledger, tmp_path)
        assert restored.values == expected
        control(restored).close()


@pytest.mark.parametrize('boundary', ['checkpoint', 'close'])
def test_checkpoint_or_close_drains_waiting_group(tmp_path, monkeypatch, boundary):
    proxy = init_persistent_system(Ledger, tmp_path, durability='sync', group_commit_delay=5)
    journal = proxy.publisher.subscribers[0]
    appended = threading.Event()
    receive = journal.receive
    def append(action):
        receive(action)
        appended.set()
    monkeypatch.setattr(journal, 'receive', append)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(proxy.add, 'before')
        assert appended.wait(5)
        if boundary == 'checkpoint':
            control(proxy).take_snapshot()
        else:
            control(proxy).close()
        future.result(timeout=2)
    control(proxy).close()
    restored = init_persistent_system(Ledger, tmp_path)
    assert restored.values == ['before']
    control(restored).close()


@pytest.mark.parametrize('codec', ['zstd', 'lz4'])
@pytest.mark.parametrize('secret', [None, b'test secret'])
@pytest.mark.parametrize('json', [False, True])
def test_compression_checkpoint_tail_and_reopen(tmp_path, codec, secret, json):
    pytest.importorskip('zstandard' if codec == 'zstd' else 'lz4.frame')
    serializer = None
    if json:
        registry = TypeRegistry()
        def decode(state):
            obj = Ledger()
            obj.values = state
            return obj
        registry.register('ledger', Ledger, encode=lambda obj: obj.values, decode=decode)
        serializer = JsonSerializer(registry)
    options = dict(secret=secret, serializer=serializer, durability='sync')
    proxy = init_persistent_system(Ledger, tmp_path, snapshot_compression=codec, **options)
    proxy.add('repeated' * 10000)
    control(proxy).take_snapshot()
    proxy.add('tail')
    control(proxy).close()
    # Compression is self-describing; next checkpoint can be uncompressed.
    restored = init_persistent_system(Ledger, tmp_path, **options)
    assert restored.values == ['repeated' * 10000, 'tail']
    control(restored).take_snapshot()
    control(restored).close()
    restored = init_persistent_system(Ledger, tmp_path, **options)
    assert restored.values == ['repeated' * 10000, 'tail']
    control(restored).close()


@pytest.mark.parametrize('codec', ['zstd', 'lz4'])
@pytest.mark.parametrize('damage', ['truncate', 'trailing', 'corrupt'])
def test_damaged_compressed_snapshots_refuse_recovery(tmp_path, codec, damage):
    pytest.importorskip('zstandard' if codec == 'zstd' else 'lz4.frame')
    proxy = init_persistent_system(Ledger, tmp_path, snapshot_compression=codec)
    control(proxy).close()
    snapshot = tmp_path / fileutils.last_snapshot_file(tmp_path)
    data = snapshot.read_bytes()
    data = data[:-2] if damage == 'truncate' else data + b'junk' if damage == 'trailing' else data[:-1] + bytes([data[-1] ^ 1])
    snapshot.write_bytes(data)
    with pytest.raises(RecoveryError):
        init_persistent_system(Ledger, tmp_path)


def test_signed_compression_authenticates_before_decompression(tmp_path, monkeypatch):
    pytest.importorskip('zstandard')
    proxy = init_persistent_system(Ledger, tmp_path, secret=b'key', snapshot_compression='zstd')
    control(proxy).close()
    snapshot = tmp_path / fileutils.last_snapshot_file(tmp_path)
    data = snapshot.read_bytes()
    snapshot.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    monkeypatch.setattr('coopy.snapshot.decompress', lambda data: pytest.fail('decoded before verification'))
    with pytest.raises(RecoveryError, match='verification'):
        init_persistent_system(Ledger, tmp_path, secret=b'key')


@pytest.mark.parametrize('codec', ['zstd', 'lz4', 'invalid'])
def test_missing_compression_dependency_or_invalid_codec(tmp_path, monkeypatch, codec):
    def missing(name):
        raise ImportError('unavailable')
    monkeypatch.setattr(importlib, 'import_module', missing)
    with pytest.raises(ConfigurationError):
        init_persistent_system(Ledger, tmp_path, snapshot_compression=codec)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('delay', [-1, float('nan'), float('inf')])
def test_invalid_batch_delay(tmp_path, delay):
    with pytest.raises(ConfigurationError):
        init_persistent_system(Ledger, tmp_path, group_commit_delay=delay)
    assert not list(tmp_path.iterdir())
