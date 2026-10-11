"""Library failures; domain exceptions still propagate unchanged."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .validation import NonDeterministicCall


class CoopyError(Exception):
    """Base class for coopy failures."""


class ConfigurationError(CoopyError, ValueError):
    """Invalid persistence configuration."""


class PrevalentError(CoopyError):
    """The domain violates persistence requirements."""


class NonDeterministicCallError(PrevalentError):
    """A domain method calls a non-deterministic source directly.

    ``cls`` and ``method`` name the method; ``calls`` lists each
    ``coopy.validation.NonDeterministicCall`` found, with its line and the
    ``self._clock``/``self._env`` replacement to use.
    """

    def __init__(self, cls: str, method: str, calls: Sequence[NonDeterministicCall]) -> None:
        self.cls = cls
        self.method = method
        self.calls = tuple(calls)
        found = "\n".join(f"  {call.describe()}" for call in self.calls)
        super().__init__(f"{cls}.{method} makes calls that replay cannot reproduce:\n{found}")


class PersistenceError(CoopyError, RuntimeError):
    """Storage failed; in-memory state may already have changed."""


class LifecycleError(CoopyError, RuntimeError):
    """An operation was attempted on a closed system."""


class ReplicationError(CoopyError, RuntimeError):
    """Replication role or synchronization prevents this operation."""


class IntegrityError(CoopyError, ValueError):
    """Storage could not be authenticated; do not deserialize it."""


class LockError(LifecycleError):
    """Another writer already holds the data directory lock."""


class FormatError(CoopyError, ValueError):
    """The data directory's on-disk format or settings do not match this open."""


class ClockDivergenceError(CoopyError, RuntimeError):
    """Replay made different clock calls than the journal recorded.

    ``index`` is the zero-based clock call within ``action``; ``expected`` and
    ``actual`` describe the recorded and the replayed call.
    """

    def __init__(self, action: str | None, index: int, expected: str, actual: str) -> None:
        self.action = action
        self.index = index
        self.expected = expected
        self.actual = actual
        where = f"action {action!r}" if action is not None else "replayed action"
        super().__init__(
            f"Clock replay diverged in {where} at clock call {index}: "
            f"expected {expected}, got {actual}"
        )
