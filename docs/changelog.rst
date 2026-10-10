.. _changelog:

Changelog
=========

Unreleased
----------

* Recovery is strict by default: detected decoding failures and replay outcome
  changes raise ``RecoveryError`` with a structured report. Explicit
  ``recovery="salvage"`` returns inspection state and a report without modifying
  persistence files. See :doc:`usage` for limitations and recovery procedures.
* ``durability="sync"`` adds journal and directory synchronization before
  acknowledging writes. Buffered durability remains the default. Journal
  persistence failures disable subsequent mutations; memory is not rolled back.
* Checkpoints coordinate snapshot publication and journal rotation under the
  proxy lock. Recovery replays only journals numbered after the checkpoint;
  older files remain available. See :doc:`snapshots`.
* Replication bootstraps a populated domain and queues catch-up actions before
  marking a replica synchronized. The authentication framing and readiness
  marker require upgrading both peers together. Replication remains experimental;
  see :doc:`replication` for unsupported durability and failover behavior.
* Type information ships with the package (``py.typed``). The proxy keeps the
  domain class type, decorators preserve signatures, and ``coopy.control``
  gives typed persistence controls. See :doc:`modern-api`.
* A writable system holds an exclusive lock on its data directory
  (``coopy.lock``) until ``close()``, context exit or process exit. A second
  writable open of the same directory, in the same or another process, raises
  ``coopy.error.LockError`` (a ``LifecycleError``). Salvage recovery does not
  take the lock. See :doc:`usage`.
* New and upgraded data directories carry a ``coopy.json`` manifest with the
  on-disk format version, serializer name, signing flag and coopy version,
  written under the directory lock. Directories without one are legacy format 0
  and gain it on the next writable open. A newer format, or reopening with a
  different serializer or signing setting, raises ``coopy.error.FormatError``
  before anything is decoded. See :doc:`usage`.
* The documentation includes executable examples checked by pytest and an
  HTML build that treats Sphinx warnings as errors.

0.5.0
-----

* Python 3.10+ only. Dropped Python 2 and the ``six`` dependency.
* Packaging moved to ``pyproject.toml``; CI moved to GitHub Actions, with
  PyPI publishing on version tags.
* Importing coopy no longer creates ``coopy.log``; the log file is set up by
  ``init_persistent_system``.
* Restore logs actions that fail on replay but succeeded originally as errors,
  and reports truncated or corrupted journal files.
* ``start_snapshot_manager`` no longer blocks the caller.
* ``shutdown()`` now closes the master server.
* Fixed master/slave replication on Python 3 (bytes handling, slave
  start-up, partial reads, clock replay on slaves).
* ``RotateFileWrapper.flush()`` works again.
* Writes no longer fail after ``start_master()`` (the master server now
  implements the full subscriber interface).
* ``validate_system`` skips methods whose source is unavailable (REPL,
  ``exec``) instead of crashing.
