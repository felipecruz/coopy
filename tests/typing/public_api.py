from typing import TYPE_CHECKING

from typing_extensions import assert_type

import coopy
from coopy.decorators import abort_exception, readonly, unlocked
from coopy.restore import RecoveryReport, RecoveryResult


class Todo:
    @readonly
    @unlocked
    @abort_exception
    def add(self, text: str, *, priority: int = 0) -> int:
        return priority


if TYPE_CHECKING:

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
    assert_type(
        coopy.convert("data", "json-data", new_serializer=coopy.JsonSerializer(), new_secret=None),
        RecoveryReport,
    )
    assert_type(coopy.open(Todo(), recovery="salvage"), RecoveryResult[Todo])
    mode: str = "strict"
    assert_type(coopy.open(Todo, recovery=mode), Todo | RecoveryResult[Todo])
    assert_type(coopy.open(Todo(), recovery=mode), Todo | RecoveryResult[Todo])
