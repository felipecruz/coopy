"""F22: one writable system per data directory."""

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import coopy
from coopy import AsyncPersistent
from coopy.decorators import readonly
from coopy.error import LifecycleError, LockError
from coopy.locking import LOCK_FILE
from tests.domain import Wiki

ROOT = Path(__file__).resolve().parents[2]

HOLDER = """
import sys
import coopy
from tests.domain import Wiki
system = coopy.open(Wiki, sys.argv[1])
system.create_page("held", "by child", None)
print("ready", flush=True)
sys.stdin.readline()
coopy.control(system).close()
"""


class Counter:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1
        return self.value

    @readonly
    def read(self):
        return self.value


def start_holder(path):
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path)],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout.readline().strip() == "ready"
    return holder


def test_same_process_double_open_fails_and_close_releases(tmp_path):
    system = coopy.open(Counter, tmp_path)
    system.increment()
    with pytest.raises(LockError) as caught:
        coopy.open(Counter, tmp_path)
    assert isinstance(caught.value, LifecycleError)
    assert str(tmp_path.resolve()) in str(caught.value)
    assert f"PID {os.getpid()}" in str(caught.value)
    # The failed open must not disturb the holder.
    assert system.increment() == 2
    coopy.control(system).close()
    reopened = coopy.open(Counter, str(tmp_path))
    assert reopened.read() == 2
    coopy.control(reopened).close()


def test_equivalent_paths_share_one_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with coopy.open(Counter, tmp_path / "data"):
        with pytest.raises(LockError):
            coopy.open(Counter, "./data/../data")


def test_context_manager_exit_releases_lock(tmp_path):
    with pytest.raises(ValueError):
        with coopy.open(Counter, tmp_path) as system:
            system.increment()
            raise ValueError("body")
    with coopy.control(coopy.open(Counter, tmp_path)) as system:
        assert system.read() == 1


def test_failed_open_releases_lock(tmp_path):
    with coopy.open(Counter, tmp_path) as system:
        system.increment()
    with pytest.raises(Exception) as caught:
        coopy.open(Counter, tmp_path, secret=b"k" * 32)  # unsigned data, signed open
    assert not isinstance(caught.value, LockError)
    with coopy.open(Counter, tmp_path):
        pass


def test_cross_process_double_open_reports_holder_pid(tmp_path):
    holder = start_holder(tmp_path)
    try:
        with pytest.raises(LockError, match=f"PID {holder.pid}"):
            coopy.open(Wiki, tmp_path)
    finally:
        holder.communicate("\n", timeout=10)
    assert holder.returncode == 0
    with coopy.open(Wiki, tmp_path) as system:
        assert system.get_page("held").content == "by child"


@pytest.mark.skipif(not hasattr(signal, "SIGKILL"), reason="requires SIGKILL")
def test_killed_holder_releases_lock(tmp_path):
    holder = start_holder(tmp_path)
    os.kill(holder.pid, signal.SIGKILL)
    holder.communicate(timeout=10)
    with coopy.open(Wiki, tmp_path) as system:
        assert system.get_page("held").content == "by child"


def test_salvage_reads_while_writer_holds_lock(tmp_path):
    with coopy.open(Counter, tmp_path) as system:
        system.increment()
        result = coopy.open(Counter, tmp_path, recovery="salvage")
        assert result.system.value == 1
        # Salvage did not take or disturb the writer's lock.
        assert system.increment() == 2
        with pytest.raises(LockError):
            coopy.open(Counter, tmp_path)


def test_salvage_does_not_create_lock_file(tmp_path):
    coopy.open(Counter, tmp_path / "missing", recovery="salvage")
    assert not (tmp_path / "missing" / LOCK_FILE).exists()


def test_async_persistent_follows_the_same_rule(tmp_path):
    async def scenario():
        async with AsyncPersistent(Counter, tmp_path) as system:
            await system.increment()
            with pytest.raises(LockError):
                await AsyncPersistent.open(Counter, tmp_path)
            with pytest.raises(LockError):
                coopy.open(Counter, tmp_path)
        async with AsyncPersistent(Counter, tmp_path) as system:
            assert await system.read() == 1

    asyncio.run(scenario())


def test_replicas_follow_the_same_rule(tmp_path):
    primary = coopy.open(Counter, tmp_path / "primary")
    replica = coopy.open(Counter, tmp_path / "replica")
    try:
        primary.increment()
        coopy.control(primary).start_primary(port=0)
        address = primary.master.server.getsockname()
        with pytest.raises(LockError):
            coopy.open(Counter, tmp_path / "primary")
        receiver = coopy.control(replica).start_replica(*address)
        assert receiver.wait_until_synchronized(3)
        assert replica.read() == 1
        with pytest.raises(LockError):
            coopy.open(Counter, tmp_path / "replica")
    finally:
        coopy.control(replica).close()
        coopy.control(primary).close()
    with coopy.open(Counter, tmp_path / "replica"):
        pass
