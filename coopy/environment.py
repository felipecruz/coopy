"""Recorded random numbers, UUIDs and tokens for ``self._env`` (F39)."""

import base64
import random as _random
import secrets
import uuid
from collections.abc import Callable, MutableSequence, Sequence
from contextvars import ContextVar
from typing import Any, Protocol, TypeVar, cast

from .foundation import RecordClock, RestoreClock

T = TypeVar("T")
V = TypeVar("V")

# secrets.DEFAULT_ENTROPY, which ``secrets`` does not export publicly
DEFAULT_NBYTES = 32


class Env(Protocol):
    """The ``self._env`` interface injected into domain objects.

    Annotate domains with ``_env: coopy.Env``. Live calls receive a
    ``RecordEnv`` that journals every value next to the clock values; recovery
    and replicas receive a ``RestoreEnv`` that returns them again.
    """

    def random(self) -> float:
        """Like ``random.random()``: a float in ``[0.0, 1.0)``."""
        ...

    def uniform(self, a: float, b: float) -> float:
        """Like ``random.uniform(a, b)``."""
        ...

    def randint(self, a: int, b: int) -> int:
        """Like ``random.randint(a, b)``, both ends included."""
        ...

    def choice(self, seq: Sequence[T]) -> T:
        """Like ``random.choice(seq)``."""
        ...

    def shuffle(self, items: MutableSequence[Any]) -> None:
        """Like ``random.shuffle(items)``, in place."""
        ...

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        """Like ``random.sample(population, k)``."""
        ...

    def uuid4(self) -> uuid.UUID:
        """Like ``uuid.uuid4()``."""
        ...

    def token_bytes(self, nbytes: int | None = None) -> bytes:
        """Like ``secrets.token_bytes(nbytes)``."""
        ...

    def token_hex(self, nbytes: int | None = None) -> str:
        """Like ``secrets.token_hex(nbytes)``."""
        ...

    def token_urlsafe(self, nbytes: int | None = None) -> str:
        """Like ``secrets.token_urlsafe(nbytes)``."""
        ...


class SystemEnv:
    """The default ``Env`` source: OS entropy through ``random.SystemRandom``."""

    def __init__(self) -> None:
        self._rng = _random.SystemRandom()

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
        return uuid.uuid4()

    def token_bytes(self, nbytes: int | None = None) -> bytes:
        return secrets.token_bytes(nbytes)

    def token_hex(self, nbytes: int | None = None) -> str:
        return secrets.token_hex(nbytes)

    def token_urlsafe(self, nbytes: int | None = None) -> str:
        return secrets.token_urlsafe(nbytes)


# shared by every RecordEnv without a source; SystemRandom keeps no state
SYSTEM_ENV = SystemEnv()


def _nbytes(nbytes: int | None) -> int:
    return DEFAULT_NBYTES if nbytes is None else nbytes


def _urlsafe_length(nbytes: int) -> int:
    return len(base64.urlsafe_b64encode(bytes(nbytes)).rstrip(b"="))


class RecordEnv:
    """Records each value in the action's clock record so replay returns it.

    Values share the clock's ``(method, value)`` list, in call order.
    ``choice``, ``shuffle`` and ``sample`` record positions rather than
    elements, so replay hands back the domain's own objects and the journal
    never copies them. ``uuid4()`` is recorded as its string form.
    """

    # a class default keeps the entropy source out of any pickled copy
    _source: Env = SYSTEM_ENV

    def __init__(self, clock: RecordClock, source: Env | None = None) -> None:
        self._clock = clock
        if source is not None:
            self._source = source

    def _record(self, method: str, value: Any) -> None:
        self._clock.results.append((method, value))

    def random(self) -> float:
        value = self._source.random()
        self._record("random", value)
        return value

    def uniform(self, a: float, b: float) -> float:
        value = self._source.uniform(a, b)
        self._record("uniform", value)
        return value

    def randint(self, a: int, b: int) -> int:
        value = self._source.randint(a, b)
        self._record("randint", value)
        return value

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise IndexError("Cannot choose from an empty sequence")
        index = self._source.choice(range(len(seq)))
        self._record("choice", index)
        return seq[index]

    def shuffle(self, items: MutableSequence[Any]) -> None:
        order = self._source.sample(range(len(items)), len(items))
        self._record("shuffle", order)
        items[:] = [items[i] for i in order]

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        indexes = self._source.sample(range(len(population)), k)
        self._record("sample", indexes)
        return [population[i] for i in indexes]

    def uuid4(self) -> uuid.UUID:
        value = self._source.uuid4()
        self._record("uuid4", str(value))
        return value

    def token_bytes(self, nbytes: int | None = None) -> bytes:
        value = self._source.token_bytes(nbytes)
        self._record("token_bytes", value)
        return value

    def token_hex(self, nbytes: int | None = None) -> str:
        value = self._source.token_hex(nbytes)
        self._record("token_hex", value)
        return value

    def token_urlsafe(self, nbytes: int | None = None) -> str:
        value = self._source.token_urlsafe(nbytes)
        self._record("token_urlsafe", value)
        return value


# the RecordEnv of the proxy call running in this thread or task (F41)
current_env: ContextVar[RecordEnv | None] = ContextVar("coopy_env", default=None)


class CallEnv:
    """The ``_env`` a proxy injects: each call records into its own clock.

    Like ``CallClock``, the ``RecordEnv`` of a call lives in a context
    variable, so concurrent ``@unlocked`` calls never record into each
    other's action. Outside a proxy call values come from OS entropy and are
    not recorded.
    """

    def _current(self) -> Env:
        env = current_env.get()
        return env if env is not None else SYSTEM_ENV

    def random(self) -> float:
        return self._current().random()

    def uniform(self, a: float, b: float) -> float:
        return self._current().uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._current().randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._current().choice(seq)

    def shuffle(self, items: MutableSequence[Any]) -> None:
        self._current().shuffle(items)

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        return self._current().sample(population, k)

    def uuid4(self) -> uuid.UUID:
        return self._current().uuid4()

    def token_bytes(self, nbytes: int | None = None) -> bytes:
        return self._current().token_bytes(nbytes)

    def token_hex(self, nbytes: int | None = None) -> str:
        return self._current().token_hex(nbytes)

    def token_urlsafe(self, nbytes: int | None = None) -> str:
        return self._current().token_urlsafe(nbytes)


# shared by every proxy; holds no state of its own
CALL_ENV = CallEnv()


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_indexes(value: list[Any], size: int, count: int) -> bool:
    return (
        len(value) == count
        and len(set(value)) == count
        and all(_is_int(i) and 0 <= i < size for i in value)
    )


def _is_uuid4(value: str) -> bool:
    try:
        return uuid.UUID(value).version == 4
    except ValueError:
        return False


class RestoreEnv:
    """Replays recorded environment values through the action's ``RestoreClock``.

    Replay must make the same calls in the same order as the original run,
    interleaved with clock calls; a different call, or a recorded value the
    replayed arguments could not have produced (``randint(1, 6)`` finding
    ``9``, ``token_hex(8)`` finding 32 characters), raises
    ``ClockDivergenceError``.
    """

    def __init__(self, clock: RestoreClock) -> None:
        self._clock = clock

    def _replay(self, method: str, actual: str, kind: type[V], valid: Callable[[V], bool]) -> V:
        value = self._clock.replay_recorded(method, actual, lambda v: type(v) is kind and valid(v))
        return cast(V, value)

    def random(self) -> float:
        return self._replay("random", "random()", float, lambda v: 0.0 <= v < 1.0)

    def uniform(self, a: float, b: float) -> float:
        low, high = min(a, b), max(a, b)
        return self._replay("uniform", f"uniform({a!r}, {b!r})", float, lambda v: low <= v <= high)

    def randint(self, a: int, b: int) -> int:
        return self._replay("randint", f"randint({a!r}, {b!r})", int, lambda v: a <= v <= b)

    def choice(self, seq: Sequence[T]) -> T:
        size = len(seq)
        index = self._replay("choice", f"choice(<{size} items>)", int, lambda v: 0 <= v < size)
        return seq[index]

    def shuffle(self, items: MutableSequence[Any]) -> None:
        size = len(items)
        order = self._replay(
            "shuffle", f"shuffle(<{size} items>)", list, lambda v: _is_indexes(v, size, size)
        )
        items[:] = [items[i] for i in order]

    def sample(self, population: Sequence[T], k: int) -> list[T]:
        size = len(population)
        indexes = self._replay(
            "sample", f"sample(<{size} items>, {k!r})", list, lambda v: _is_indexes(v, size, k)
        )
        return [population[i] for i in indexes]

    def uuid4(self) -> uuid.UUID:
        return uuid.UUID(self._replay("uuid4", "uuid4()", str, _is_uuid4))

    def token_bytes(self, nbytes: int | None = None) -> bytes:
        size = _nbytes(nbytes)
        return self._replay(
            "token_bytes", f"token_bytes({nbytes!r})", bytes, lambda v: len(v) == size
        )

    def token_hex(self, nbytes: int | None = None) -> str:
        size = 2 * _nbytes(nbytes)
        return self._replay("token_hex", f"token_hex({nbytes!r})", str, lambda v: len(v) == size)

    def token_urlsafe(self, nbytes: int | None = None) -> str:
        size = _urlsafe_length(_nbytes(nbytes))
        return self._replay(
            "token_urlsafe", f"token_urlsafe({nbytes!r})", str, lambda v: len(v) == size
        )
