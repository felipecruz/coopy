"""Run unchanged on GIL and free-threaded builds: require coherent queries."""

import os
import sys
import sysconfig
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from coopy import control
from coopy import open as open_persistent
from coopy.decorators import readonly


class Ledger:
    def __init__(self):
        self.values = []
        self.count = 0

    def add(self, value):
        self.values.append(value)
        # Force an observable inconsistent intermediate state without the lock.
        time.sleep(0.0001)
        self.count += 1

    @readonly
    def read(self):
        return self.count, tuple(self.values)


def test_ci_really_has_no_gil():
    if os.environ.get("COOPY_REQUIRE_NO_GIL") != "1":
        pytest.skip("GIL-disabled assertion is required in free-threaded CI")
    assert sysconfig.get_config_var("Py_GIL_DISABLED") == 1
    assert not sys._is_gil_enabled()


@pytest.mark.parametrize("delay", [0, 0.001])
def test_concurrent_readers_writers_and_checkpoints(tmp_path, delay):
    with control(
        open_persistent(Ledger, tmp_path, durability="sync", group_commit_delay=delay)
    ) as ledger:
        barrier = threading.Barrier(7)
        # Writers cannot finish until every reader has queried live state.
        readers_ready = threading.Barrier(6)

        def write(worker):
            barrier.wait(timeout=5)
            ledger.add((worker, 0))
            readers_ready.wait(timeout=5)
            for index in range(1, 40):
                ledger.add((worker, index))

        def read():
            barrier.wait(timeout=5)
            count, values = ledger.read()
            assert count == len(values)
            readers_ready.wait(timeout=5)
            for _ in range(100):
                count, values = ledger.read()
                assert count == len(values) == len(set(values))
                time.sleep(0.0001)

        def checkpoints():
            barrier.wait(timeout=5)
            for _ in range(10):
                control(ledger).take_snapshot()
                time.sleep(0.0001)

        with ThreadPoolExecutor(7) as pool:
            futures = [pool.submit(write, worker) for worker in range(3)]
            futures += [pool.submit(read) for _ in range(3)]
            futures.append(pool.submit(checkpoints))
            for future in futures:
                future.result(timeout=20)
        expected = ledger.read()
        assert expected[0] == 120
    with control(open_persistent(Ledger, tmp_path)) as restored:
        assert restored.read() == expected
