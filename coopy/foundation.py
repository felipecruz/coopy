from datetime import date, datetime, timezone
from typing import Any

from .error import ClockDivergenceError
from .validation import DATE_FUNCS, DATETIME_FUNCS


class RecordClock(object):
    def __init__(self) -> None:
        self.results: list[date] = []

    def __getattr__(self, name: str) -> Any:
        if name in DATETIME_FUNCS:
            return getattr(datetime, name)
        elif name in DATE_FUNCS:
            return getattr(date, name)
        return object.__getattribute__(self, name)

    def now(self) -> datetime:
        dt = datetime.now()
        self.results.append(dt)
        return dt

    def utcnow(self) -> datetime:
        # naive UTC datetime, same as the deprecated datetime.utcnow()
        dt = datetime.now(timezone.utc).replace(tzinfo=None)
        self.results.append(dt)
        return dt

    def today(self) -> date:
        dt = date.today()
        self.results.append(dt)
        return dt


class RestoreClock(object):
    """Replays recorded clock values and detects divergent clock calls.

    Journals store bare values, so ``now()`` and ``utcnow()`` (both
    ``datetime``) cannot be told apart; ``today()`` records a plain ``date``.
    The first divergence is kept so a domain method that swallows it still
    fails replay through ``check_calls``/``check_complete``.
    """

    def __init__(self, results: list[date], action: str | None = None) -> None:
        self.results = list(results)
        self.action = action
        self.index = 0
        self.divergence: ClockDivergenceError | None = None

    def now(self) -> datetime:
        return self._replay("now")

    def utcnow(self) -> datetime:
        return self._replay("utcnow")

    def today(self) -> date:
        return self._replay("today")

    def _replay(self, method_name: str) -> Any:
        if self.divergence is not None:
            raise self.divergence
        actual = f"{method_name}()"
        if self.index >= len(self.results):
            self._diverge(f"no call ({len(self.results)} recorded)", actual)
        value = self.results[self.index]
        if method_name in DATETIME_FUNCS:
            matches = isinstance(value, datetime)
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


def _recorded_call(value: Any) -> str:
    if isinstance(value, datetime):
        return f"now() or utcnow() returning {value!r}"
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
        self.results: list[date] | None = None
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
