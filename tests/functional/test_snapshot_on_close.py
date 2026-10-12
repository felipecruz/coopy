"""F32: optionally snapshot on close."""

import pytest

from coopy import fileutils
from coopy.base import control, init_persistent_system


class Accumulator:
    def __init__(self):
        self.total = 0

    def add(self, n):
        self.total += n


class TestCloseWithSnapshot:
    def test_default_close_no_snapshot(self, tmp_path):
        proxy = init_persistent_system(Accumulator, str(tmp_path))
        proxy.add(10)
        proxy.close()
        logs = fileutils.list_log_files(tmp_path)
        snapshots = fileutils.list_snapshot_files(tmp_path)
        # Only the initial snapshot, no extra
        assert len(snapshots) == 1
        assert logs is not None

    def test_close_with_snapshot(self, tmp_path):
        proxy = init_persistent_system(Accumulator, str(tmp_path))
        proxy.add(10)
        proxy.add(20)
        proxy.close(snapshot=True)
        snapshots = fileutils.list_snapshot_files(tmp_path)
        assert len(snapshots) == 2  # initial + close snapshot
        # Next open should replay no actions
        proxy2 = init_persistent_system(Accumulator, str(tmp_path))
        assert proxy2.obj.total == 30
        assert proxy2.recovery_report.replayed == 0
        proxy2.close()

    def test_close_snapshot_false_is_default(self, tmp_path):
        proxy = init_persistent_system(Accumulator, str(tmp_path))
        proxy.add(5)
        proxy.close(snapshot=False)
        snapshots = fileutils.list_snapshot_files(tmp_path)
        assert len(snapshots) == 1

    def test_close_snapshot_failure_leaves_previous_usable(self, tmp_path):
        proxy = init_persistent_system(Accumulator, str(tmp_path))
        proxy.add(42)

        # Sabotage the snapshot manager to simulate a failure
        def fail_take(*a, **kw):
            raise OSError("disk full")

        proxy.snapshot_manager.take_snapshot = fail_take
        # close(snapshot=True) should report the error but still close cleanly
        with pytest.raises(OSError, match="disk full"):
            proxy.close(snapshot=True)
        # The data directory is still intact and recoverable
        proxy2 = init_persistent_system(Accumulator, str(tmp_path))
        assert proxy2.obj.total == 42
        proxy2.close()

    def test_double_close_is_idempotent(self, tmp_path):
        proxy = init_persistent_system(Accumulator, str(tmp_path))
        proxy.add(1)
        proxy.close(snapshot=True)
        proxy.close(snapshot=True)  # should not raise


class TestContextManagerWithSnapshot:
    def test_context_manager_default_no_snapshot(self, tmp_path):
        with init_persistent_system(Accumulator, str(tmp_path)) as proxy:
            proxy.add(10)
        snapshots = fileutils.list_snapshot_files(tmp_path)
        assert len(snapshots) == 1

    def test_context_manager_with_snapshot_on_close(self, tmp_path):
        ctl = control(init_persistent_system(Accumulator, str(tmp_path)))
        ctl.snapshot_on_close = True
        with ctl as proxy:
            proxy.add(10)
            proxy.add(20)
        snapshots = fileutils.list_snapshot_files(tmp_path)
        assert len(snapshots) == 2
        # Next open replays no actions
        proxy2 = init_persistent_system(Accumulator, str(tmp_path))
        assert proxy2.obj.total == 30
        assert proxy2.recovery_report.replayed == 0
        proxy2.close()


class TestControlCloseWithSnapshot:
    def test_control_close_snapshot(self, tmp_path):
        proxy = init_persistent_system(Accumulator, str(tmp_path))
        ctl = control(proxy)
        ctl.close(snapshot=True)
        snapshots = fileutils.list_snapshot_files(tmp_path)
        assert len(snapshots) == 2

    def test_control_close_default(self, tmp_path):
        proxy = init_persistent_system(Accumulator, str(tmp_path))
        ctl = control(proxy)
        proxy.add(5)
        ctl.close()
        snapshots = fileutils.list_snapshot_files(tmp_path)
        assert len(snapshots) == 1
