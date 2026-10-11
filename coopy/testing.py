"""Deterministic clocks and environments for testing ``self._clock`` and ``self._env``."""

import base64
import random
import uuid
from collections.abc import MutableSequence, Sequence
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, TypeVar

from .base import CoopyProxy
from .environment import DEFAULT_NBYTES, SYSTEM_ENV, Env
from .foundation import Clock, RecordClock

__all__ = ["FrozenClock", "ManualClock", "SeededEnv", "install_clock", "install_env"]

T = TypeVar("T")


class FrozenClock:
    """A ``coopy.Clock`` that always returns ``dt``.

    ``now()`` and ``utcnow()`` both return ``dt`` unchanged and ``today()``
    returns ``dt.date()``. ``now(tz)`` converts an aware ``dt`` to ``tz`` and
    attaches ``tz`` to a naive one. ``time()`` is ``dt.timestamp()`` (a naive
    ``dt`` counts as local time) and ``monotonic()`` stays at ``0.0``.
    """

    def __init__(self, dt: datetime) -> None:
        self._dt = dt
        self._elapsed = 0.0

    def now(self, tz: tzinfo | None = None) -> datetime:
        if tz is None:
            return self._dt
        if self._dt.tzinfo is None:
            return self._dt.replace(tzinfo=tz)
        return self._dt.astimezone(tz)

    def utcnow(self) -> datetime:
        return self._dt

    def today(self) -> date:
        return self._dt.date()

    def time(self) -> float:
        return self._dt.timestamp()

    def monotonic(self) -> float:
        return self._elapsed


class ManualClock(FrozenClock):
    """A ``coopy.Clock`` that only moves when the test moves it.

    ``monotonic()`` counts the seconds passed to ``advance()``; ``set()`` does
    not move it, so it never goes backwards.
    """

    def __init__(self, start: datetime) -> None:
        super().__init__(start)

    def advance(self, delta: timedelta) -> datetime:
        """Move forward by ``delta`` and return the new time."""
        if delta < timedelta(0):
            raise ValueError("advance() requires a non-negative timedelta; use set()")
        self._dt += delta
        self._elapsed += delta.total_seconds()
        return self._dt

    def set(self, dt: datetime) -> None:
        """Jump to ``dt``, forwards or backwards."""
        self._dt = dt


def install_clock(system: Any, clock: Clock | None) -> None:
    """Make ``system``'s ``self._clock`` read from ``clock``.

    For a system returned by ``coopy.open`` every later method call records
    the values ``clock`` returns, so they are journaled and replay on restart
    and on replicas like real clock values. For a plain domain object (not
    opened through coopy) ``clock`` is injected as ``_clock`` directly.
    ``clock=None`` restores the real clock.
    """
    if isinstance(system, CoopyProxy):
        system._clock_source = clock
    else:
        # bypass any __setattr__, like coopy.utils.inject
        system.__dict__["_clock"] = clock if clock is not None else RecordClock()


class SeededEnv:
    """A ``coopy.Env`` whose values all come from ``random.Random(seed)``.

    The same seed gives the same sequence of numbers, UUIDs and tokens, so
    tests can assert exact values. Tokens are predictable: never use this
    outside tests.
    """

    def __init__(self, seed: int | str | bytes = 0) -> None:
        self._rng = random.Random(seed)

    def random(self) -> float:
        return self._rng.random()

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._rng.choice(seq)

    def shuffle(self, items: MutableSequence[Any]) -> None:
        self._rng.shuffle(items)

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        return self._rng.sample(population, k)

    def uuid4(self) -> uuid.UUID:
        return uuid.UUID(int=self._rng.getrandbits(128), version=4)

    def token_bytes(self, nbytes: int | None = None) -> bytes:
        size = DEFAULT_NBYTES if nbytes is None else nbytes
        return self._rng.getrandbits(8 * size).to_bytes(size, "big") if size else b""

    def token_hex(self, nbytes: int | None = None) -> str:
        return self.token_bytes(nbytes).hex()

    def token_urlsafe(self, nbytes: int | None = None) -> str:
        return base64.urlsafe_b64encode(self.token_bytes(nbytes)).rstrip(b"=").decode("ascii")


def install_env(system: Any, env: Env | None) -> None:
    """Make ``system``'s ``self._env`` read from ``env``.

    For a system returned by ``coopy.open`` every later method call records
    the values ``env`` returns, so they replay on restart and on replicas;
    ``env`` itself is never stored. For a plain domain object ``env`` is
    injected as ``_env`` directly. ``env=None`` restores OS entropy.
    """
    if isinstance(system, CoopyProxy):
        system._env_source = env
    else:
        # bypass any __setattr__, like coopy.utils.inject
        system.__dict__["_env"] = env if env is not None else SYSTEM_ENV
