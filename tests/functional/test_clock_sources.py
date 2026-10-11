"""now(tz), time() and monotonic() are recorded and replay exactly (F37)."""

import struct
from datetime import datetime, timedelta, timezone

import pytest

import coopy
from coopy.base import CoopyProxy
from coopy.cli import summarize
from coopy.error import ClockDivergenceError
from coopy.foundation import Action, RecordClock, RestoreClock
from coopy.network.network import COPYNET_HEADER, prepare_data
from coopy.testing import FrozenClock, ManualClock, install_clock
from coopy.validation import validate_date_datetime_calls, validate_system
from tests.unit.test_network_select import fake_master as fake_master
from tests.unit.test_network_select import wait_for

BRASILIA = timezone(timedelta(hours=-3))


class Jobs:
    _clock: coopy.Clock

    def __init__(self):
        self.runs = []

    def run(self, name):
        started = self._clock.monotonic()
        stamp = self._clock.now(timezone.utc)
        local = self._clock.now(BRASILIA)
        epoch = self._clock.time()
        duration = self._clock.monotonic() - started
        self.runs.append((name, stamp, local, epoch, duration))


def decode_jobs(state):
    jobs = object.__new__(Jobs)
    jobs.__dict__.update(state)
    return jobs


def json_serializer():
    registry = coopy.TypeRegistry()
    registry.register("jobs", Jobs, encode=lambda j: dict(vars(j)), decode=decode_jobs)
    return coopy.JsonSerializer(registry)


def assert_offsets(runs):
    for _, stamp, local, epoch, duration in runs:
        assert stamp.utcoffset() == timedelta(0)
        assert local.utcoffset() == timedelta(hours=-3)
        assert type(epoch) is float and duration >= 0.0


@pytest.mark.parametrize("make_serializer", [coopy.PickleSerializer, json_serializer])
@pytest.mark.parametrize("snapshot", [False, True])
def test_aware_and_float_values_round_trip_storage(tmp_path, make_serializer, snapshot):
    serializer = make_serializer()
    with coopy.control(coopy.open(Jobs, basedir=str(tmp_path), serializer=serializer)) as jobs:
        jobs.run("a")
        if snapshot:
            coopy.control(jobs).take_snapshot()
        jobs.run("b")
        live = list(jobs.runs)
    assert_offsets(live)

    with coopy.control(coopy.open(Jobs, basedir=str(tmp_path), serializer=serializer)) as jobs:
        assert jobs.runs == live
        assert [run[2].isoformat() for run in jobs.runs] == [run[2].isoformat() for run in live]
        assert_offsets(jobs.runs)


def test_test_clock_values_replay_exactly(tmp_path):
    clock = ManualClock(datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
    with coopy.control(coopy.open(Jobs, basedir=str(tmp_path))) as jobs:
        install_clock(jobs, clock)
        jobs.run("a")
        clock.advance(timedelta(seconds=90))
        jobs.run("b")
        live = list(jobs.runs)
    assert live[1][1] == datetime(2026, 1, 1, 12, 1, 30, tzinfo=timezone.utc)
    assert live[1][2].hour == 9
    assert live[1][3] - live[0][3] == 90.0
    with coopy.control(coopy.open(Jobs, basedir=str(tmp_path))) as jobs:
        assert jobs.runs == live


def test_replica_replays_aware_values_with_offset(fake_master):  # noqa: F811
    proxy, slave, peer = fake_master
    source = CoopyProxy(Jobs(), [])
    source.run("a")
    action = Action(1, "run", datetime(2020, 1, 1), ("a",), {})
    action.results = list(source.obj._clock.results)
    action.raised = False
    for value in (Jobs(), action):
        header, payload = prepare_data(value)
        peer.sendall(header + payload)
    peer.sendall(struct.pack(COPYNET_HEADER, 0, b"r"))
    assert slave.wait_until_synchronized(3)
    wait_for(lambda: len(proxy.obj.runs) == 1)
    assert proxy.obj.runs == source.obj.runs
    assert_offsets(proxy.obj.runs)
    source.close()


def test_naive_now_still_records_naive_values():
    clock = RecordClock()
    assert clock.now().tzinfo is None
    assert clock.utcnow().tzinfo is None
    assert clock.now(timezone.utc).tzinfo is timezone.utc
    assert [type(clock.time()), type(clock.monotonic())] == [float, float]
    assert len(clock.results) == 5


def test_restore_clock_replays_new_sources():
    aware = datetime(2026, 1, 1, tzinfo=BRASILIA)
    clock = RestoreClock([aware, 1.5, 2.5, aware], "act")
    assert clock.now(timezone.utc) is aware  # the recorded value, unconverted
    assert clock.time() == 1.5
    assert clock.monotonic() == 2.5
    assert clock.now() is aware
    clock.check_complete()


DIVERGENT = {
    "naive for now(tz)": ([datetime(2026, 1, 1)], "now", "naive", "now(datetime.timezone.utc)"),
    "date for time()": ([datetime(2026, 1, 1).date()], "time", "today()", "time()"),
    "float for now()": ([1.5], "now", "time() or monotonic()", "now()"),
    "float for today()": ([1.5], "today", "time() or monotonic()", "today()"),
    "int for monotonic()": ([1], "monotonic", "found int", "monotonic()"),
    "aware for today()": (
        [datetime(2026, 1, 1, tzinfo=timezone.utc)],
        "today",
        "now(tz)",
        "today()",
    ),
}


@pytest.mark.parametrize("case", DIVERGENT)
def test_restore_clock_detects_divergent_new_sources(case):
    results, method, expected, actual = DIVERGENT[case]
    clock = RestoreClock(results, "act")
    call = getattr(clock, method)
    with pytest.raises(ClockDivergenceError) as caught:
        call(timezone.utc) if actual.startswith("now(datetime") else call()
    assert expected in caught.value.expected
    assert caught.value.actual == actual


def test_validator_accepts_new_clock_calls():
    code = """
def run(self):
    a = self._clock.now(timezone.utc)
    b = self._clock.now(tz=timezone.utc)
    c = self._clock.time()
    d = self._clock.monotonic() - self._clock.monotonic()
    """
    assert validate_date_datetime_calls(code)
    assert not validate_date_datetime_calls("def run(self):\n    datetime.now(timezone.utc)\n")
    assert validate_system(Jobs())


def test_test_clock_sources():
    naive = FrozenClock(datetime(2026, 1, 1, 12))
    assert naive.now(timezone.utc) == datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert naive.time() == datetime(2026, 1, 1, 12).timestamp()
    assert naive.monotonic() == 0.0

    aware = FrozenClock(datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
    assert aware.now() is aware.now(None)
    assert aware.now(BRASILIA).isoformat() == "2026-01-01T09:00:00-03:00"
    assert aware.time() == 1767268800.0

    manual = ManualClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    manual.advance(timedelta(seconds=5))
    manual.set(datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert manual.monotonic() == 5.0
    manual.advance(timedelta(seconds=1))
    assert manual.monotonic() == 6.0


def test_legacy_sources_without_tz_still_work():
    class OldSource:
        def now(self):
            return datetime(2020, 1, 1)

    clock = RecordClock(OldSource())
    assert clock.now() == datetime(2020, 1, 1)


def test_cli_log_shows_float_clock_values():
    action = Action(1, "run", datetime(2020, 1, 1), ("a",), {})
    action.results = [datetime(2020, 1, 1, tzinfo=timezone.utc), 1.5]
    action.raised = False
    assert "clock=[2020-01-01T00:00:00+00:00, 1.5]" in summarize(action)
