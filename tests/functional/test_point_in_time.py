"""F31: restore to a point in time using action count or datetime bounds."""

from datetime import datetime, timedelta

import pytest

import coopy
from coopy.base import init_persistent_system
from coopy.error import ConfigurationError
from coopy.restore import RecoveryResult, replay


class Counter:
    def __init__(self):
        self.value = 0
        self.timestamps = []

    def increment(self):
        self.value += 1
        self.timestamps.append(self._clock.now())


def populate(tmp_path, n=5):
    """Create a system with n increments and return the timestamps."""
    proxy = init_persistent_system(Counter, str(tmp_path))
    for _ in range(n):
        proxy.increment()
    proxy.close()


class TestUntilActionCount:
    def test_replay_first_n_actions(self, tmp_path):
        populate(tmp_path, 5)
        result = init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=3
        )
        assert isinstance(result, RecoveryResult)
        assert result.system.value == 3
        assert result.report.replayed == 3
        assert result.report.bounded is True
        assert result.report.complete

    def test_replay_all_when_until_exceeds_count(self, tmp_path):
        populate(tmp_path, 3)
        result = init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=10
        )
        assert result.system.value == 3
        assert result.report.replayed == 3
        assert result.report.bounded is False

    def test_replay_zero_actions(self, tmp_path):
        """until=0 is invalid; action counts are one-based."""
        populate(tmp_path, 3)
        with pytest.raises(ConfigurationError, match="until action count must be >= 1"):
            init_persistent_system(
                Counter, str(tmp_path), recovery="salvage", until=0
            )

    def test_replay_exactly_all(self, tmp_path):
        populate(tmp_path, 3)
        result = init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=3
        )
        assert result.system.value == 3
        assert result.report.replayed == 3

    def test_nothing_written(self, tmp_path):
        populate(tmp_path, 5)
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=2
        )
        after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert before == after


class TestUntilDatetime:
    def test_replay_up_to_time(self, tmp_path):
        proxy = init_persistent_system(Counter, str(tmp_path))
        proxy.increment()
        proxy.increment()
        # Get the timestamp of the second action
        ts2 = proxy.obj.timestamps[1]
        proxy.increment()
        proxy.close()

        # Replay up to the timestamp of the second action
        result = init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=ts2
        )
        assert result.system.value == 2
        assert result.report.replayed == 2
        assert result.report.bounded is True

    def test_replay_all_with_future_bound(self, tmp_path):
        populate(tmp_path, 3)
        future = datetime(2099, 1, 1)
        result = init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=future
        )
        assert result.system.value == 3
        assert result.report.bounded is False

    def test_replay_none_with_past_bound(self, tmp_path):
        populate(tmp_path, 3)
        past = datetime(2000, 1, 1)
        result = init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=past
        )
        assert result.system.value == 0
        assert result.report.replayed == 0
        assert result.report.bounded is True

    def test_nothing_written(self, tmp_path):
        populate(tmp_path, 3)
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        init_persistent_system(
            Counter, str(tmp_path), recovery="salvage", until=datetime(2000, 1, 1)
        )
        after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert before == after


class TestReplayFunction:
    def test_replay_with_action_count(self, tmp_path):
        populate(tmp_path, 5)
        result = replay(Counter, str(tmp_path), until=3)
        assert isinstance(result, RecoveryResult)
        assert result.system.value == 3
        assert result.report.replayed == 3
        assert result.report.bounded is True

    def test_replay_without_bound(self, tmp_path):
        populate(tmp_path, 3)
        result = replay(Counter, str(tmp_path))
        assert result.system.value == 3
        assert result.report.replayed == 3

    def test_replay_with_datetime(self, tmp_path):
        proxy = init_persistent_system(Counter, str(tmp_path))
        proxy.increment()
        ts1 = proxy.obj.timestamps[0]
        proxy.increment()
        proxy.close()

        result = replay(Counter, str(tmp_path), until=ts1)
        assert result.system.value == 1
        assert result.report.bounded is True

    def test_replay_nothing_written(self, tmp_path):
        populate(tmp_path, 3)
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        replay(Counter, str(tmp_path), until=1)
        after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert before == after

    def test_replay_from_module(self, tmp_path):
        populate(tmp_path, 3)
        result = coopy.replay(Counter, str(tmp_path), until=2)
        assert result.system.value == 2

    def test_replay_accepts_instance(self, tmp_path):
        populate(tmp_path, 3)
        result = replay(Counter(), str(tmp_path), until=2)
        assert result.system.value == 2


class TestUntilValidation:
    def test_until_requires_salvage(self, tmp_path):
        populate(tmp_path, 3)
        with pytest.raises(ConfigurationError, match="until requires recovery='salvage'"):
            init_persistent_system(
                Counter, str(tmp_path), recovery="strict", until=2
            )

    def test_invalid_until_type(self, tmp_path):
        populate(tmp_path, 3)
        with pytest.raises(ConfigurationError, match="until must be"):
            replay(Counter, str(tmp_path), until="bad")

    def test_negative_action_count(self, tmp_path):
        populate(tmp_path, 3)
        with pytest.raises(ConfigurationError, match="until action count must be >= 1"):
            replay(Counter, str(tmp_path), until=-1)


class TestPointInTimeAfterSnapshot:
    def test_replay_after_checkpoint(self, tmp_path):
        """Actions after a snapshot are still replayable."""
        proxy = init_persistent_system(Counter, str(tmp_path))
        proxy.increment()
        proxy.increment()
        proxy.take_snapshot()
        proxy.increment()
        proxy.increment()
        proxy.increment()
        proxy.close()

        # Replay 4 actions total: 2 pre-snapshot (in snapshot state) + 2 post
        result = replay(Counter, str(tmp_path), until=2)
        # The snapshot contains value=2, and we replay 2 post-snapshot actions
        assert result.system.value == 4
        assert result.report.replayed == 2

    def test_replay_zero_post_snapshot(self, tmp_path):
        """With until=0 invalid, but until=N where N covers snapshot state only."""
        proxy = init_persistent_system(Counter, str(tmp_path))
        proxy.increment()
        proxy.increment()
        proxy.take_snapshot()
        proxy.increment()
        proxy.close()

        # Replay with datetime before the post-snapshot action
        ts = proxy.obj.timestamps[1]  # timestamp of second action (in snapshot)
        result = replay(Counter, str(tmp_path), until=ts)
        # Snapshot state is value=2, post-snapshot action has later timestamp
        assert result.system.value == 2
        assert result.report.replayed == 0
        assert result.report.bounded is True
