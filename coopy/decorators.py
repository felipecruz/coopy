from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def unlocked(func: Callable[P, R]) -> Callable[P, R]:
    setattr(func, "__unlocked", True)
    return func


def readonly(func: Callable[P, R]) -> Callable[P, R]:
    setattr(func, "__readonly", True)
    return func


def abort_exception(func: Callable[P, R]) -> Callable[P, R]:
    """Skip journaling failed calls; successful non-readonly calls are recorded.

    Exceptions still reach the caller. This does not roll back in-memory
    mutations or external effects, and later snapshots can retain mutations
    made before a failure. Combined with readonly, neither outcome is recorded.
    """
    setattr(func, "__abort_exception", True)
    return func
