import time as _time
from datetime import date, datetime, timezone, tzinfo
from typing import Any, Protocol

from .error import ClockDivergenceError
from .validation import DATETIME_FUNCS


class Clock(Protocol):
    """The ``self._clock`` interface injected into domain objects.

    Annotate domains with ``_clock: coopy.Clock``: coopy injects a
    ``RecordClock`` for live calls and a ``RestoreClock`` during recovery and
    on replicas, and both implement this protocol.
    """

    def now(self, tz: tzinfo | None = None) -> datetime:
        """Like ``datetime.now(tz)``: naive local time, or aware in ``tz``."""
        ...

    def utcnow(self) -> datetime:
        """Naive UTC ``datetime`` (no timezone attached)."""
        ...

    def today(self) -> date:
        """Local ``date``."""
        ...

    def time(self) -> float:
        """Seconds since the epoch, like ``time.time()``."""
        ...

    def monotonic(self) -> float:
        """Like ``time.monotonic()``; only differences within one call are meaningful."""
        ...


class RecordClock(object):
    """Records each clock value so journal replay can return it again.

    ``source`` (for example a ``coopy.testing`` clock) supplies the values
    instead of the system clock.
    """

    # a class default keeps ``source`` out of the serialized state
    source: Clock | None = None

    def __init__(self, source: Clock | None = None) -> None:
        self.results: list[date | float] = []
        if source is not None:
            self.source = source

    def now(self, tz: tzinfo | None = None) -> datetime:
        if self.source is None:
            dt = datetime.now(tz)
        elif tz is None:
            # sources written before tz support take no argument
            dt = self.source.now()
        else:
            dt = self.source.now(tz)
        self.results.append(dt)
        return dt

    def utcnow(self) -> datetime:
        if self.source is None:
            # naive UTC datetime, same as the deprecated datetime.utcnow()
            dt = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            dt = self.source.utcnow()
        self.results.append(dt)
        return dt

    def today(self) -> date:
        dt = date.today() if self.source is None else self.source.today()
        self.results.append(dt)
        return dt

    def time(self) -> float:
        value = _time.time() if self.source is None else self.source.time()
        self.results.append(value)
        return value

    def monotonic(self) -> float:
        value = _time.monotonic() if self.source is None else self.source.monotonic()
        self.results.append(value)
        return value


class RestoreClock(object):
    """Replays recorded clock values and detects divergent clock calls.

    Journals store bare values, so ``now()`` and ``utcnow()`` (both
    ``datetime``) cannot be told apart, nor ``time()`` and ``monotonic()``
    (both ``float``); ``today()`` records a plain ``date``. ``now(tz)`` with a
    timezone requires an aware recorded value.
    The first divergence is kept so a domain method that swallows it still
    fails replay through ``check_calls``/``check_complete``.
    """

    def __init__(self, results: list[date | float], action: str | None = None) -> None:
        self.results = list(results)
        self.action = action
        self.index = 0
        self.divergence: ClockDivergenceError | None = None

    def now(self, tz: tzinfo | None = None) -> datetime:
        if tz is None:
            return self._replay("now")
        return self._replay("now", f"now({tz!r})", aware=True)

    def utcnow(self) -> datetime:
        return self._replay("utcnow")

    def today(self) -> date:
        return self._replay("today")

    def time(self) -> float:
        return self._replay("time")

    def monotonic(self) -> float:
        return self._replay("monotonic")

    def _replay(self, method_name: str, actual: str | None = None, aware: bool = False) -> Any:
        if self.divergence is not None:
            raise self.divergence
        actual = actual or f"{method_name}()"
        if self.index >= len(self.results):
            self._diverge(f"no call ({len(self.results)} recorded)", actual)
        value = self.results[self.index]
        if method_name in DATETIME_FUNCS:
            matches = isinstance(value, datetime) and (not aware or value.tzinfo is not None)
        elif method_name in FLOAT_FUNCS:
            matches = type(value) is float
        else:
            matches = isinstance(value, date) and not isinstance(value, datetime)
        if not matches:
            self._diverge(_recorded_call(value), actual)
        self.index += 1
        return value

    def _diverge(self, expected: str, actual: str) -> None:
        self.divergence = ClockDivergenceError(self.action, self.index, expected, actual)
        raise self.divergence

    def check_calls(self) -> None:
        """Raise the first divergence a clock call detected, if any."""
        if self.divergence is not None:
            raise self.divergence

    def check_complete(self) -> None:
        """Also fail when replay left recorded clock values unused."""
        self.check_calls()
        if self.index < len(self.results):
            self.divergence = ClockDivergenceError(
                self.action,
                self.index,
                _recorded_call(self.results[self.index]),
                f"no call ({self.index} replayed)",
            )
            raise self.divergence


FLOAT_FUNCS = ("time", "monotonic")


def _recorded_call(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return f"now() or utcnow() returning naive {value!r}"
        return f"now(tz) returning {value!r}"
    if type(value) is float:
        return f"time() or monotonic() returning {value!r}"
    if isinstance(value, date):
        return f"today() returning {value!r}"
    return f"a clock value, found {type(value).__name__} {value!r}"


class VersionedState(object):
    """Snapshot envelope: the root object and its class's ``__coopy_version__``.

    Only written for classes that declare the attribute, so unversioned
    snapshots keep the 0.6.0 layout and count as version 1.
    """

    def __init__(self, version: int, state: Any) -> None:
        self.version = version
        self.state = state


class Action(object):
    def __init__(
        self,
        caller_id: int,
        action: str,
        timestamp: datetime,
        args: tuple[Any, ...] | list[Any],
        kwargs: dict[str, Any],
    ) -> None:
        self.schema_version = 1
        self.caller_id = caller_id
        self.action = action
        self.args = args
        self.kwargs = kwargs
        self.results: list[date | float] | None = None
        self.raised: bool | None = None

        # TODO do we need it?
        self.timestamp = timestamp

    def __str__(self) -> str:
        return "action %s \ncaller_id %s \nargs %s" % (self.action, str(self.caller_id), self.args)

    def execute_action(self, system: Any) -> Any:
        # TODO not reliable
        method = getattr(system, self.action)
        return method(*self.args, **self.kwargs)


class Publisher:
    def __init__(self, subscribers: list[Any]) -> None:
        self.subscribers = subscribers

    def register(self, subscriber: Any) -> None:
        self.subscribers.append(subscriber)

    def publish(self, message: Action) -> None:
        for subscriber in self.subscribers:
            subscriber.receive(message)

    def publish_before(self, message: Action) -> None:
        for subscriber in self.subscribers:
            subscriber.receive_before(message)

    def publish_exception(self, message: Action) -> None:
        for subscriber in self.subscribers:
            subscriber.receive_exception(message)

    def close(self) -> None:
        for subscriber in self.subscribers:
            subscriber.close()
