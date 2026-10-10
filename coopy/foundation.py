from datetime import date, datetime, timezone
from typing import Any, Callable

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
    def __init__(self, results: list[date]) -> None:
        # reverse order!
        self.results = results[::-1]

    def __getattr__(self, name: str) -> Any:
        if name in DATETIME_FUNCS or name in DATE_FUNCS:
            return self.pop_and_check(name)
        return object.__getattribute__(self, name)

    def pop_and_check(self, method_name: str) -> Callable[[], date] | None:
        last_element = self.results[-1]
        if method_name in DATETIME_FUNCS:
            if not isinstance(last_element, datetime):
                raise TypeError("This call returns a %s" % (datetime.__class__))
            return lambda: self.results.pop()
        elif method_name in DATE_FUNCS:
            if not isinstance(last_element, date):
                raise TypeError("This call returns a %s" % (date.__class__))
            return lambda: self.results.pop()
        return None


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
