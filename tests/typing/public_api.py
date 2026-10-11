from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from typing_extensions import assert_type

import coopy
from coopy.decorators import abort_exception, readonly, unlocked
from coopy.foundation import RecordClock, RestoreClock
from coopy.restore import RecoveryReport, RecoveryResult
from coopy.testing import FrozenClock, ManualClock, install_clock


class Todo:
    @readonly
    @unlocked
    @abort_exception
    def add(self, text: str, *, priority: int = 0) -> int:
        return priority


class Journal:
    _clock: coopy.Clock

    def __init__(self) -> None:
        self.entries: list[tuple[datetime, datetime, date]] = []

    def record(self) -> datetime:
        entry = (self._clock.now(), self._clock.utcnow(), self._clock.today())
        self.entries.append(entry)
        return entry[0]


class LegacyJournal:
    _clock: RecordClock

    def stamp(self) -> date:
        return self._clock.today()


if TYPE_CHECKING:
    clock: coopy.Clock = RecordClock()
    clock = RestoreClock([])
    assert_type(clock.now(), datetime)
    assert_type(clock.utcnow(), datetime)
    assert_type(clock.today(), date)
    assert_type(clock.now(timezone.utc), datetime)
    assert_type(clock.now(tz=None), datetime)
    assert_type(clock.time(), float)
    assert_type(clock.monotonic(), float)
    clock.now("UTC")  # type: ignore[arg-type]
    clock.yesterday()  # type: ignore[attr-defined]
    RecordClock().yesterday()  # type: ignore[attr-defined]
    RestoreClock([]).yesterday()  # type: ignore[attr-defined]
    assert_type(RecordClock().now(), datetime)
    assert_type(RestoreClock([]).today(), date)
    clock = FrozenClock(datetime(2026, 1, 1))
    manual = ManualClock(datetime(2026, 1, 1))
    clock = manual
    assert_type(manual.advance(timedelta(hours=1)), datetime)
    assert_type(manual.set(datetime(2026, 1, 2)), None)
    assert_type(manual.today(), date)
    manual.advance(3600)  # type: ignore[arg-type]
    assert_type(manual.now(timezone.utc), datetime)
    assert_type(manual.monotonic(), float)
    FrozenClock(datetime(2026, 1, 1)).yesterday()  # type: ignore[attr-defined]
    RecordClock(manual).now()
    journal = coopy.open(Journal)
    assert_type(journal.record(), datetime)
    install_clock(journal, manual)
    install_clock(Journal(), None)
    assert_type(coopy.open(LegacyJournal).stamp(), date)

    async def async_api() -> None:
        async with coopy.AsyncPersistent(Todo, "async-data") as todo:
            await todo.add("milk")
            await todo.call("add", "eggs")
            await todo.take_snapshot()
        opened = await coopy.AsyncPersistent.open(Todo, "async-data")
        await opened.aclose()

    a = coopy.init_persistent_system(Todo)
    b = coopy.init_persistent_system(Todo())
    assert_type(a, Todo)
    assert_type(b, Todo)
    assert_type(a.add("milk", priority=1), int)
    a.add(1)  # type: ignore[arg-type]
    a.add("milk", 1)  # type: ignore[misc]
    result = coopy.init_persistent_system(Todo, recovery="salvage")
    assert_type(result, RecoveryResult[Todo])
    assert_type(result.system, Todo | None)
    from coopy.snapshot import SnapshotJob

    coopy.control(a).take_snapshot()
    assert_type(coopy.control(a).take_snapshot(mode="fork", fork_safe=True), SnapshotJob | None)
    assert_type(coopy.open(Todo, snapshot_compression="zstd", group_commit_delay=0.002), Todo)
    coopy.control(b).close()
    with coopy.control(coopy.open(Todo)) as managed:
        assert_type(managed, Todo)
        assert_type(managed.add("milk"), int)
    assert_type(
        coopy.open(Todo, serializer=coopy.JsonSerializer(), schemas=coopy.ActionSchemas()), Todo
    )
    assert_type(coopy.open(Todo, state_schemas=coopy.StateSchemas()), Todo)
    assert_type(coopy.open(Todo, secret=[b"new-key", b"old-key"]), Todo)
    assert_type(
        coopy.convert("data", "json-data", new_serializer=coopy.JsonSerializer(), new_secret=None),
        RecoveryReport,
    )
    assert_type(coopy.control(managed).prune(keep=2).removed, list[str])
    assert_type(coopy.prune("data", keep=1, keep_for=None).snapshots, list[str])
    assert_type(coopy.open(Todo(), recovery="salvage"), RecoveryResult[Todo])
    mode: str = "strict"
    assert_type(coopy.open(Todo, recovery=mode), Todo | RecoveryResult[Todo])
    assert_type(coopy.open(Todo(), recovery=mode), Todo | RecoveryResult[Todo])
