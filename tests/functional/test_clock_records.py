"""Journals record which clock call produced each value (F38)."""

import json
import pickle
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import coopy
from coopy import manifest
from coopy.base import init_persistent_system
from coopy.cli import summarize
from coopy.error import ClockDivergenceError, FormatError
from coopy.foundation import RECORD_VERSION, RestoreClock
from coopy.manifest import MANIFEST_FILE
from coopy.restore import RecoveryError
from coopy.testing import ManualClock, install_clock
from tests.clock_domain import Agenda
from tests.functional.test_clock_divergence import STAMP, Calendar, action, fixture
from tests.functional.test_manifest import contents, forbid_decoding

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "legacy" / "v0_6_clock"
BRASILIA = timezone(timedelta(hours=-3))
CALLS = ["monotonic", "now", "utcnow", "now", "today", "time", "monotonic"]

# What the format 1 fixture (written by the F37 commit) restored, values as recorded.
LEGACY_ENTRIES = [
    (
        name,
        datetime(2026, 1, 1, 12, minute),
        datetime(2026, 1, 1, 12, minute),
        datetime(2026, 1, 1, 12, minute, tzinfo=timezone.utc),
        date(2026, 1, 1),
        epoch,
        0.0,
    )
    for name, minute, epoch in [("first", 0, 1767265200.0), ("second", 5, 1767265500.0)]
]


def decode_agenda(state):
    agenda = object.__new__(Agenda)
    agenda.__dict__.update(state)
    return agenda


def json_serializer():
    registry = coopy.TypeRegistry()
    registry.register("agenda", Agenda, encode=lambda a: dict(vars(a)), decode=decode_agenda)
    return coopy.JsonSerializer(registry)


def journal_actions(path, serializer=None):
    actions = []
    for log in sorted(Path(path).glob("transaction_*.log")):
        with log.open("rb") as stream:
            reader = pickle.Unpickler(stream) if serializer is None else serializer.reader(stream)
            while True:
                try:
                    actions.append(reader.load())
                except EOFError:
                    break
    return actions


@pytest.mark.parametrize("make_serializer", [lambda: None, json_serializer])
def test_new_journals_record_call_names(tmp_path, make_serializer):
    serializer = make_serializer()
    with coopy.control(coopy.open(Agenda, basedir=tmp_path, serializer=serializer)) as agenda:
        install_clock(agenda, ManualClock(datetime(2026, 1, 1, 12)))
        agenda.stamp("a")
        live = list(agenda.entries)
    (record,) = journal_actions(tmp_path, serializer)
    assert record.record_version == RECORD_VERSION == 2
    assert [method for method, _ in record.results] == CALLS
    assert [value for _, value in record.results][1:6] == list(live[0][1:6])
    assert "now=2026-01-01T12:00:00" in summarize(record)
    stored = json.loads((tmp_path / MANIFEST_FILE).read_text())
    assert stored["format_version"] == manifest.FORMAT_VERSION == 2
    with coopy.open(Agenda, basedir=tmp_path, serializer=serializer) as agenda:
        assert agenda.entries == live


def test_format_1_fixture_replays_and_upgrades_manifest(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    (legacy,) = [a for a in journal_actions(data) if a.action == "stamp"][:1]
    assert not hasattr(legacy, "record_version") and type(legacy.results[0]) is float

    result = coopy.open(Agenda, data, recovery="salvage")
    assert result.report.complete and result.system.entries == LEGACY_ENTRIES
    assert json.loads((data / MANIFEST_FILE).read_text())["format_version"] == 1

    with coopy.open(Agenda, data) as agenda:
        assert agenda.entries == LEGACY_ENTRIES
        agenda.stamp("third")
        live = list(agenda.entries)
    assert json.loads((data / MANIFEST_FILE).read_text())["format_version"] == 2
    # the journal now mixes bare-value and (method, value) records
    versions = [getattr(a, "record_version", 1) for a in journal_actions(data)]
    assert versions == [1, 1, 2]
    with coopy.open(Agenda, data) as agenda:
        assert agenda.entries == live


# (recorded entries, replayed method, expected text, actual text)
SWAPPED = {
    "utcnow for now": ([("now", STAMP)], "utcnow", "now() returning", "utcnow()"),
    "now for utcnow": ([("utcnow", STAMP)], "now", "utcnow() returning", "now()"),
    "monotonic for time": ([("time", 1.5)], "monotonic", "time() returning 1.5", "monotonic()"),
    "today for now": ([("now", STAMP)], "today", "now() returning", "today()"),
    "unknown call": ([("random", 0.5)], "time", "random() returning 0.5", "time()"),
}


@pytest.mark.parametrize("case", SWAPPED)
def test_divergence_names_recorded_and_replayed_call(case):
    results, method, expected, actual = SWAPPED[case]
    clock = RestoreClock(results, "act")
    with pytest.raises(ClockDivergenceError) as caught:
        getattr(clock, method)()
    assert caught.value.expected.startswith(expected)
    assert caught.value.actual == actual


def test_now_tz_must_match_the_recorded_offset():
    aware = datetime(2026, 1, 1, 9, tzinfo=BRASILIA)
    assert RestoreClock([("now", aware)]).now(timezone(timedelta(hours=-3))) is aware
    clock = RestoreClock([("now", aware)], "act")
    with pytest.raises(ClockDivergenceError) as caught:
        clock.now(timezone.utc)
    assert caught.value.expected.startswith("now(tz) returning")
    assert caught.value.actual == f"now({timezone.utc!r})"
    # legacy bare values keep F37 behavior: the value is returned unconverted
    assert RestoreClock([aware]).now(timezone.utc) is aware
    assert RestoreClock([1.5]).monotonic() == 1.5


def test_strict_recovery_reports_both_calls(tmp_path):
    good = action("stamp", [("now", STAMP)], "first")
    fixture(tmp_path, [good, action("stamp", [("utcnow", STAMP)])])
    with pytest.raises(RecoveryError) as caught:
        init_persistent_system(Calendar, str(tmp_path), recovery="strict")
    divergence = caught.value.__cause__
    assert isinstance(divergence, ClockDivergenceError)
    assert divergence.expected.startswith("utcnow() returning")
    assert divergence.actual == "now()"
    assert caught.value.report.stop.kind == "clock"


def test_newer_action_record_version_is_refused(tmp_path):
    record = action("stamp", [("now", STAMP)])
    record.record_version = RECORD_VERSION + 1
    fixture(tmp_path, [record])
    with pytest.raises(RecoveryError) as caught:
        init_persistent_system(Calendar, str(tmp_path), recovery="strict")
    assert isinstance(caught.value.__cause__, FormatError)
    assert "record version 3" in str(caught.value.__cause__)


@pytest.mark.parametrize("mode", ["strict", "salvage"])
def test_older_reader_refuses_new_format_through_manifest(tmp_path, monkeypatch, mode):
    with coopy.open(Agenda, basedir=tmp_path) as agenda:
        agenda.stamp("a")
    before = contents(tmp_path)
    # a coopy that only knows format 1 (the F37 release) reading this directory
    monkeypatch.setattr(manifest, "FORMAT_VERSION", 1)
    forbid_decoding(monkeypatch)
    with pytest.raises(FormatError, match="format 2, newer than format 1.*upgrade coopy"):
        coopy.open(Agenda, basedir=tmp_path, recovery=mode)
    assert contents(tmp_path) == before
