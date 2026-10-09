from typing import TYPE_CHECKING
from typing_extensions import assert_type
import coopy
from coopy.decorators import readonly, unlocked, abort_exception
from coopy.restore import RecoveryResult

class Todo:
    @readonly
    @unlocked
    @abort_exception
    def add(self, text: str, *, priority: int = 0) -> int:
        return priority

if TYPE_CHECKING:
    a = coopy.init_persistent_system(Todo)
    b = coopy.init_persistent_system(Todo())
    assert_type(a, Todo)
    assert_type(b, Todo)
    assert_type(a.add('milk', priority=1), int)
    a.add(1)  # type: ignore[arg-type]
    a.add('milk', 1)  # type: ignore[misc]
    result = coopy.init_persistent_system(Todo, recovery='salvage')
    assert_type(result, RecoveryResult[Todo])
    assert_type(result.system, Todo | None)
    coopy.control(a).take_snapshot()
    coopy.control(b).close()
    with coopy.control(coopy.open(Todo)) as managed:
        assert_type(managed, Todo)
        assert_type(managed.add("milk"), int)
    assert_type(coopy.open(Todo, serializer=coopy.JsonSerializer(), schemas=coopy.ActionSchemas()), Todo)
    assert_type(coopy.open(Todo(), recovery="salvage"), RecoveryResult[Todo])
    mode: str = "strict"
    assert_type(coopy.open(Todo, recovery=mode), Todo | RecoveryResult[Todo])
    assert_type(coopy.open(Todo(), recovery=mode), Todo | RecoveryResult[Todo])
