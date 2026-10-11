"""Validation resolves imports and flags every non-deterministic source (F40)."""

import logging

import pytest

import coopy
from coopy.error import ConfigurationError, NonDeterministicCallError, PrevalentError
from coopy.validation import find_calls, validate_system
from tests import validation_domain as fixtures

PATTERNS = sorted(fixtures.PATTERNS.items(), key=lambda item: item[0].__name__)


@pytest.mark.parametrize(
    ("domain", "expected"), PATTERNS, ids=[domain.__name__ for domain, _ in PATTERNS]
)
def test_strict_flags_each_pattern(domain, expected):
    written, source, replacement = expected
    with pytest.raises(NonDeterministicCallError) as raised:
        validate_system(domain(), "strict")
    error = raised.value
    assert isinstance(error, PrevalentError)
    assert (error.cls, error.method) == (domain.__name__, "run")
    [call] = error.calls
    assert (call.written, call.source, call.replacement) == expected
    assert call.filename == fixtures.__file__
    assert "return" in open(fixtures.__file__).read().splitlines()[call.line - 1]
    assert f"{written}()" in str(error)


@pytest.mark.parametrize(
    ("domain", "expected"), PATTERNS, ids=[domain.__name__ for domain, _ in PATTERNS]
)
def test_warn_keeps_previous_behavior(domain, expected, caplog):
    # Only datetime.now()/date.today() written that way were rejected before.
    if domain is fixtures.DateToday:
        with pytest.raises(NonDeterministicCallError):
            validate_system(domain())
        return
    with caplog.at_level(logging.WARNING, logger="coopy.validation"):
        assert validate_system(domain())
    assert f"{domain.__name__}.run calls {expected[0]}()" in caplog.text
    assert expected[2] in caplog.text


def test_off_skips_validation(caplog):
    with caplog.at_level(logging.WARNING, logger="coopy.validation"):
        for domain in fixtures.PATTERNS:
            assert validate_system(domain(), "off")
    assert caplog.text == ""


@pytest.mark.parametrize("policy", ["warn", "strict"])
def test_clock_and_env_calls_are_accepted(policy, caplog):
    with caplog.at_level(logging.WARNING, logger="coopy.validation"):
        assert validate_system(fixtures.Deterministic(), policy)
    assert caplog.text == ""


def test_methods_without_source_are_skipped_with_warning(caplog):
    namespace = {}
    exec(
        "import time\nclass NoSource:\n    def method(self):\n        return time.time()\n",
        namespace,
    )
    with caplog.at_level(logging.WARNING, logger="coopy.validation"):
        assert validate_system(namespace["NoSource"](), "strict")
    assert "Could not validate method: source code not available" in caplog.text


def test_unknown_policy_is_rejected():
    with pytest.raises(ConfigurationError, match="validation must be"):
        validate_system(fixtures.Deterministic(), "loud")


def test_strict_reports_every_call():
    source = """
def run(self):
    import random as r
    a = r.random()
    b = self._env.random()
    c = clock.now()
    d = uuid.uuid1()
    e = random.Random(3).random()
"""
    calls = find_calls(source)
    assert [(c.written, c.source, c.line) for c in calls] == [
        ("r.random", "random.random", 4),
        ("uuid.uuid1", "uuid.uuid1", 7),
    ]


def test_open_applies_policy(tmp_path):
    with pytest.raises(NonDeterministicCallError, match="uuid.uuid4"):
        coopy.open(fixtures.Uuid4, basedir=str(tmp_path / "strict"), validation="strict")
    with pytest.raises(ConfigurationError, match="validation must be"):
        coopy.open(fixtures.Uuid4, basedir=str(tmp_path / "bad"), validation="loud")
    with pytest.raises(NonDeterministicCallError, match="date.today"):
        coopy.open(fixtures.DateToday, basedir=str(tmp_path / "warn"))
    with coopy.control(
        coopy.open(fixtures.DateToday, basedir=str(tmp_path / "off"), validation="off")
    ) as system:
        assert system.run()
    with coopy.control(coopy.open(fixtures.Uuid4, basedir=str(tmp_path / "default"))) as system:
        assert system.run()


def test_async_open_passes_policy(tmp_path):
    import asyncio

    async def open_strict():
        await coopy.AsyncPersistent.open(fixtures.Uuid4, str(tmp_path), validation="strict")

    with pytest.raises(NonDeterministicCallError):
        asyncio.run(open_strict())
