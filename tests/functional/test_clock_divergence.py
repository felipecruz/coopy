"""Replay must fail with ClockDivergenceError when clock calls differ."""

import pickle
import struct
from datetime import date, datetime
from pathlib import Path

import pytest

import coopy
from coopy.base import init_persistent_system
from coopy.error import ClockDivergenceError, CoopyError
from coopy.foundation import Action, RestoreClock
from coopy.network.network import COPYNET_HEADER, prepare_data
from coopy.restore import RecoveryError
from tests.unit.test_network_select import fake_master as fake_master

STAMP = datetime(2020, 1, 2, 3, 4, 5)
DAY = date(2020, 1, 2)


class Calendar:
    def __init__(self):
        self.events = []

    def stamp(self, name):
        self.events.append((name, self._clock.now()))

    def day(self, name):
        self.events.append((name, self._clock.today()))

    def swallow(self, name):
        try:
            self.events.append((name, self._clock.now()))
        except Exception:
            self.events.append((name, None))


def action(name, results, arg="x"):
    result = Action(1, name, datetime(2020, 1, 1), (arg,), {})
    result.results = results
    result.raised = False
    return result


def fixture(tmp_path, records):
    proxy = init_persistent_system(Calendar, str(tmp_path))
    journal = Path(proxy.publisher.subscribers[0].file.name)
    proxy.close()
    with journal.open("wb") as file:
        pickler = pickle.Pickler(file, protocol=2)
        offsets = []
        for record in records:
            offsets.append(file.tell())
            pickler.dump(record)
    return journal, offsets


# (method, recorded results, call index, expected text, actual text)
DIVERGENT = {
    "wrong method": ("day", [STAMP], 0, "now() or utcnow()", "today()"),
    "wrong type": ("stamp", [DAY], 0, "today() returning", "now()"),
    "foreign value": ("stamp", ["2020-01-02"], 0, "found str", "now()"),
    "too many calls": ("stamp", [], 0, "no call (0 recorded)", "now()"),
    "too few calls": ("stamp", [STAMP, STAMP], 1, "now() or utcnow()", "no call (1 replayed)"),
    "swallowed": ("swallow", [], 0, "no call (0 recorded)", "now()"),
}


@pytest.mark.parametrize("case", DIVERGENT)
def test_divergent_clock_calls_stop_strict_and_salvage(tmp_path, case):
    method, results, index, expected, actual = DIVERGENT[case]
    good = action("stamp", [STAMP], "first")
    journal, offsets = fixture(tmp_path, [good, action(method, results)])
    with pytest.raises(RecoveryError) as caught:
        init_persistent_system(Calendar, str(tmp_path), recovery="strict")
    divergence = caught.value.__cause__
    assert isinstance(divergence, ClockDivergenceError)
    assert isinstance(divergence, CoopyError)
    assert (divergence.action, divergence.index) == (method, index)
    assert expected in divergence.expected and actual == divergence.actual
    assert f"action {method!r}" in str(divergence)
    assert f"clock call {index}" in str(divergence)
    report = caught.value.report
    assert report.stop.kind == "clock"
    assert report.stop.detail == str(divergence)
    assert report.stop.state_may_be_changed
    assert report.replayed == 1

    result = init_persistent_system(Calendar, str(tmp_path), recovery="salvage")
    position = result.report.stop.position
    assert (position.file, position.offset, position.record, position.action) == (
        str(journal),
        offsets[1],
        2,
        method,
    )
    assert result.report.stop.detail == str(divergence)
    assert result.system.events[0] == ("first", STAMP)


def test_divergence_wins_over_expected_failure(tmp_path):
    record = action("day", [STAMP])
    record.raised = True
    fixture(tmp_path, [record])
    with pytest.raises(RecoveryError) as caught:
        init_persistent_system(Calendar, str(tmp_path))
    assert caught.value.report.stop.kind == "clock"
    assert caught.value.report.expected_failures == 0


def test_correct_journals_replay_unchanged(tmp_path):
    records = [
        action("stamp", [STAMP], "a"),
        action("day", [DAY], "b"),
        action("swallow", [STAMP], "c"),
    ]
    fixture(tmp_path, records)
    proxy = init_persistent_system(Calendar, str(tmp_path))
    try:
        assert proxy.events == [("a", STAMP), ("b", DAY), ("c", STAMP)]
        assert proxy.recovery_report.complete
        assert proxy.recovery_report.replayed == 3
        proxy.stamp("d")
        proxy.day("e")
        live = list(proxy.events)
    finally:
        proxy.close()
    reopened = init_persistent_system(Calendar, str(tmp_path))
    try:
        assert reopened.events == live
    finally:
        reopened.close()


def test_restore_clock_reports_each_divergence():
    clock = RestoreClock([STAMP, DAY], "act")
    assert clock.utcnow() == STAMP
    assert clock.today() == DAY
    clock.check_complete()
    with pytest.raises(ClockDivergenceError, match="clock call 2: expected no call"):
        clock.now()
    with pytest.raises(ClockDivergenceError) as caught:
        clock.today()  # the first divergence sticks
    assert caught.value.actual == "now()"
    assert coopy.ClockDivergenceError is ClockDivergenceError


@pytest.mark.parametrize("case", ["wrong method", "too many calls", "too few calls"])
def test_replica_becomes_unsynchronized_with_same_message(fake_master, case):  # noqa: F811
    method, results, index, expected, actual = DIVERGENT[case]
    proxy, slave, peer = fake_master
    initial = proxy.obj
    record = action(method, results)
    for value in (Calendar(), record):
        header, payload = prepare_data(value)
        peer.sendall(header + payload)
    peer.sendall(struct.pack(COPYNET_HEADER, 0, b"r"))
    slave.join(3)
    assert not slave.is_alive()
    assert not slave.synchronized
    clock = RestoreClock(results, method)
    with pytest.raises(ClockDivergenceError) as caught:
        target = Calendar()
        target._clock = clock
        try:
            getattr(target, method)("x")
        finally:
            clock.check_complete()
    assert slave.error == str(caught.value)
    assert proxy.obj is initial
