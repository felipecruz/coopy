"""coopy.testing clocks drive self._clock without sleeping (F36)."""

from datetime import date, datetime, timedelta

import pytest

import coopy
from coopy.decorators import readonly
from coopy.foundation import RecordClock
from coopy.testing import FrozenClock, ManualClock, install_clock

START = datetime(2026, 1, 1, 12, 0, 0)


class Tokens:
    _clock: coopy.Clock

    def __init__(self):
        self.issued = {}

    def issue(self, name):
        self.issued[name] = self._clock.now()

    @readonly
    def is_valid(self, name):
        return self._clock.now() - self.issued[name] < timedelta(hours=1)


def test_token_expires_after_one_hour(tmp_path):
    clock = ManualClock(START)
    with coopy.control(coopy.open(Tokens, basedir=str(tmp_path))) as tokens:
        install_clock(tokens, clock)
        tokens.issue("abc")
        clock.advance(timedelta(minutes=59, seconds=59))
        assert tokens.is_valid("abc")
        clock.advance(timedelta(seconds=1))
        assert not tokens.is_valid("abc")
        clock.set(START)
        assert tokens.is_valid("abc")


def test_test_clock_values_are_journaled_and_replayed(tmp_path):
    tokens = coopy.open(Tokens, basedir=str(tmp_path))
    install_clock(tokens, FrozenClock(START))
    tokens.issue("abc")
    coopy.control(tokens).close()

    reopened = coopy.open(Tokens, basedir=str(tmp_path))
    try:
        assert reopened.issued == {"abc": START}
        install_clock(reopened, None)
        reopened.issue("live")
        assert reopened.issued["live"] > START
    finally:
        coopy.control(reopened).close()


def decode_tokens(state):
    tokens = object.__new__(Tokens)
    tokens.__dict__.update(state)
    return tokens


def json_serializer():
    registry = coopy.TypeRegistry()
    registry.register("tokens", Tokens, encode=lambda t: dict(vars(t)), decode=decode_tokens)
    return coopy.JsonSerializer(registry)


@pytest.mark.parametrize("make_serializer", [coopy.PickleSerializer, json_serializer])
def test_snapshot_does_not_store_the_test_clock(tmp_path, make_serializer):
    serializer = make_serializer()
    tokens = coopy.open(Tokens, basedir=str(tmp_path), serializer=serializer)
    install_clock(tokens, ManualClock(START))
    tokens.issue("abc")
    coopy.control(tokens).take_snapshot()
    coopy.control(tokens).close()

    reopened = coopy.open(Tokens, basedir=str(tmp_path), serializer=serializer)
    try:
        assert reopened.issued == {"abc": START}
        assert "source" not in vars(reopened._clock)
    finally:
        coopy.control(reopened).close()


def test_install_clock_on_plain_domain():
    tokens = Tokens()
    clock = ManualClock(START)
    install_clock(tokens, clock)
    tokens.issue("abc")
    clock.advance(timedelta(hours=2))
    assert not tokens.is_valid("abc")
    install_clock(tokens, None)
    assert isinstance(tokens._clock, RecordClock)


def test_clock_methods():
    frozen = FrozenClock(START)
    assert frozen.now() == frozen.utcnow() == START
    assert frozen.today() == date(2026, 1, 1)
    assert type(frozen.today()) is date

    manual = ManualClock(START)
    assert manual.advance(timedelta(days=1)) == START + timedelta(days=1)
    assert manual.today() == date(2026, 1, 2)
    manual.set(START - timedelta(days=1))
    assert manual.now() == START - timedelta(days=1)
    with pytest.raises(ValueError):
        manual.advance(timedelta(seconds=-1))


def test_deprecated_helpers_warn_but_work(tmp_path):
    from coopy.tests.utils import TestClock, TestSystemMixin

    with pytest.warns(DeprecationWarning, match="FrozenClock"):
        legacy = TestClock(START)
    assert legacy.now() == legacy.utcnow() == legacy.today() == START

    tokens = coopy.open(Tokens, basedir=str(tmp_path))
    try:
        with pytest.warns(DeprecationWarning, match="install_clock"):
            TestSystemMixin().mock_clock(tokens, START)
        tokens.issue("abc")
        assert tokens.issued["abc"] == START
        with pytest.warns(DeprecationWarning, match="install_clock"):
            TestSystemMixin().enable_clock(tokens)
        tokens.issue("live")
        assert tokens.issued["live"] > START
    finally:
        coopy.control(tokens).close()
