"""Deterministic clocks for testing domains that use ``self._clock``."""

from datetime import date, datetime, timedelta
from typing import Any

from .base import CoopyProxy
from .foundation import Clock, RecordClock

__all__ = ["FrozenClock", "ManualClock", "install_clock"]


class FrozenClock:
    """A ``coopy.Clock`` that always returns ``dt``.

    ``now()`` and ``utcnow()`` both return ``dt`` unchanged and ``today()``
    returns ``dt.date()``.
    """

    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def now(self) -> datetime:
        return self._dt

    def utcnow(self) -> datetime:
        return self._dt

    def today(self) -> date:
        return self._dt.date()


class ManualClock(FrozenClock):
    """A ``coopy.Clock`` that only moves when the test moves it."""

    def __init__(self, start: datetime) -> None:
        super().__init__(start)

    def advance(self, delta: timedelta) -> datetime:
        """Move forward by ``delta`` and return the new time."""
        if delta < timedelta(0):
            raise ValueError("advance() requires a non-negative timedelta; use set()")
        self._dt += delta
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
