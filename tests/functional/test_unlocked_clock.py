"""Concurrent @unlocked calls each record their own clock and env values (F41)."""

import threading
from datetime import datetime, timezone

import pytest

import coopy
from coopy.decorators import unlocked
from coopy.foundation import CALL_CLOCK, RecordClock
from tests.functional.test_clock_records import journal_actions

ROUNDS = 3


class Turns:
    """Makes the test's two calls alternate; off during replay."""

    def __init__(self):
        self.barrier = None
        self.first_done = None

    def step(self):
        if self.barrier is not None:
            self.barrier.wait(timeout=5)

    def finish(self, key):
        # the second call publishes after the first, as an application must
        # arrange for unlocked writers (journal writes are not serialized)
        if self.first_done is not None and key == "b":
            assert self.first_done.wait(timeout=5)


TURNS = Turns()


class Stamps:
    _clock: coopy.Clock
    _env: coopy.Env

    def __init__(self):
        self.stamps = {}

    @unlocked
    def stamp(self, key):
        values = []
        # both calls are inside the proxy before either reads the clock
        TURNS.step()
        for _ in range(ROUNDS):
            values.append(self._clock.now(timezone.utc))
            values.append(self._env.random())
            TURNS.step()
        TURNS.finish(key)
        self.stamps[key] = values
        return values


@pytest.fixture
def turns():
    TURNS.barrier = threading.Barrier(2)
    TURNS.first_done = threading.Event()
    yield TURNS
    TURNS.barrier = None
    TURNS.first_done = None


def run_concurrently(stamps, turns):
    errors = []

    def call(key):
        try:
            stamps.stamp(key)
            if key == "a":
                turns.first_done.set()
        except BaseException as error:  # pragma: no cover - reported below
            errors.append(error)
            turns.barrier.abort()
            turns.first_done.set()

    threads = [threading.Thread(target=call, args=(key,)) for key in "ab"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not errors


def decode_stamps(state):
    stamps = object.__new__(Stamps)
    stamps.__dict__.update(state)
    return stamps


def json_serializer():
    registry = coopy.TypeRegistry()
    registry.register("stamps", Stamps, encode=lambda s: dict(vars(s)), decode=decode_stamps)
    return coopy.JsonSerializer(registry)


def test_concurrent_unlocked_calls_replay_identical_state(tmp_path, turns):
    stamps = coopy.open(Stamps, basedir=tmp_path)
    try:
        run_concurrently(stamps, turns)
        live = dict(stamps.stamps)
        obj = coopy.control(stamps)._proxy.obj
        assert "_env" not in vars(obj)
        assert vars(obj)["_clock"] is CALL_CLOCK
    finally:
        coopy.control(stamps).close()

    assert sorted(live) == ["a", "b"]
    for action in journal_actions(tmp_path):
        # each action holds exactly its own values, in call order
        (key,) = action.args
        assert [value for _, value in action.results] == live[key]
        assert [method for method, _ in action.results] == ["now", "random"] * ROUNDS

    # replay runs the calls one after the other
    turns.barrier = turns.first_done = None
    with coopy.control(coopy.open(Stamps, basedir=tmp_path)) as reopened:
        report = coopy.control(reopened).recovery_report
        assert report.complete and report.replayed == 2
        assert reopened.stamps == live


@pytest.mark.parametrize("make_serializer", [coopy.PickleSerializer, json_serializer])
def test_snapshot_stores_a_plain_record_clock(tmp_path, make_serializer):
    serializer = make_serializer()
    with coopy.control(coopy.open(Stamps, basedir=tmp_path, serializer=serializer)) as stamps:
        stamps.stamp("a")
        coopy.control(stamps).take_snapshot()
        live = dict(stamps.stamps)
    with coopy.control(coopy.open(Stamps, basedir=tmp_path, serializer=serializer)) as reopened:
        assert reopened.stamps == live
        assert type(coopy.control(reopened)._proxy.obj._clock) is RecordClock
        reopened.stamp("b")
        assert sorted(reopened.stamps) == ["a", "b"]


def test_clock_outside_a_call_is_not_recorded(tmp_path):
    with coopy.control(coopy.open(Stamps, basedir=tmp_path)) as stamps:
        stamps.stamp("a")
        obj = coopy.control(stamps)._proxy.obj
        # values read outside a proxy call are live and never journaled
        assert isinstance(obj._clock.now(), datetime)
        assert isinstance(obj._clock.time(), float)
        stamps.stamp("b")
    actions = journal_actions(tmp_path)
    assert [len(action.results) for action in actions] == [2 * ROUNDS, 2 * ROUNDS]
