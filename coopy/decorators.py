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


def transactional(func: Callable[P, R]) -> Callable[P, R]:
    """Restore the domain's state when the call fails; the failure is not journaled.

    Before each call the proxy deep-copies the domain object's attributes. If
    the method raises, or its journal record could not be written and was
    removed again, the copy replaces the attributes, so live state and state
    after a restart both equal the state before the call. Each call costs a
    copy of the whole state. Cannot be combined with readonly or unlocked.
    """
    setattr(func, "__transactional", True)
    return func
