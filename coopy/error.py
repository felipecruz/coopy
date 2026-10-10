"""Library failures; domain exceptions still propagate unchanged."""


class CoopyError(Exception):
    """Base class for coopy failures."""


class ConfigurationError(CoopyError, ValueError):
    """Invalid persistence configuration."""


class PrevalentError(CoopyError):
    """The domain violates persistence requirements."""


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
