.. _changelog:

Changelog
=========

Unreleased
----------

* Registered snapshot-state upgraders: ``coopy.StateSchemas`` and the
  ``state_schemas`` argument of ``coopy.open``/``recover``. Snapshots of a
  root class declaring ``__coopy_version__`` record that version; recovery
  runs the registered upgraders in order before journal replay, and missing
  upgraders or unknown versions fail through the recovery policy. Unversioned
  classes keep the 0.6.0 snapshot layout. A snapshot written for a versioned
  class cannot be read by 0.6.0. See :doc:`migrations`.

0.6.0 (2026-10-10)
------------------

First release published to PyPI since 0.3.1. It includes the 0.5.0 changes,
which were never tagged or published.

Upgrading
~~~~~~~~~

These changes can break existing applications or deployments:

* **Strict recovery by default.** A journal or snapshot that fails to decode,
  or a replayed action whose outcome differs from the recorded one, now raises
  ``coopy.restore.RecoveryError`` instead of being logged and skipped. Pass
  ``recovery="salvage"`` to inspect a damaged directory read-only. See
  :doc:`usage`.
* **New replication handshake.** Authentication framing and the replica
  readiness marker changed. Upgrade the primary and all replicas together;
  0.6.0 peers cannot talk to older ones. Replication stays experimental; see
  :doc:`replication`.
* **Deprecated replication names.** ``start_master`` and ``start_slave`` emit
  ``DeprecationWarning``; use ``start_primary`` and ``start_replica``. The old
  names will be removed in v0.9.
* **One writer per directory.** A second writable open of the same data
  directory raises ``coopy.error.LockError``.
* **Format manifest.** The first writable open adds ``coopy.json`` to existing
  directories; reopening with a different serializer or signing setting raises
  ``coopy.error.FormatError``.
* **Logging is opt-in.** coopy no longer writes ``coopy.log`` on import or
  initialization; call ``coopy.logging_config(directory)`` or configure the
  ``coopy`` logger in your application.
* **Python 3.10 or newer** is required.

Changes
~~~~~~~

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
* A migration guide explains when to use action upcasters, class aliases or a
  versioned ``__setstate__``, with an executable example that upgrades a
  committed old-format snapshot. See :doc:`migrations`.
* The documentation includes executable examples checked by pytest and an
  HTML build that treats Sphinx warnings as errors.
* ``coopy.open()`` is the short entry point (``init_persistent_system``
  remains), works as a context manager, accepts ``str`` and ``os.PathLike``
  directories, and failures raise a ``CoopyError`` hierarchy.
* Opt-in ``secret=`` signs every journal record and snapshot with
  HMAC-SHA256 and verifies them before unpickling.
* Pluggable serializers: pickle stays the default, a JSON serializer accepts
  registered types only, and ``ActionSchemas`` upcasters and class aliases
  migrate old journals.
* ``durability="sync"`` supports group commit (``group_commit_delay``);
  snapshots can be compressed with the ``zstd`` or ``lz4`` extras, and POSIX
  fork snapshots are available where supported. See :doc:`performance`.
* ``AsyncPersistent`` exposes awaitable domain methods backed by one writer
  thread. CI covers free-threaded Python 3.14t.
* Replication password checks use ``hmac.compare_digest``; the empty
  ``linux_epoll`` and ``osx_kqueue`` modules were removed.
* Ruff, Hypothesis state-machine tests, a coverage gate, Dependabot for
  GitHub Actions and a generated API reference were added to development.
* Dropped Python 2 and the ``six`` dependency.
* Packaging moved to ``pyproject.toml``; CI moved to GitHub Actions, with
  PyPI publishing on version tags.
* ``start_snapshot_manager`` no longer blocks the caller.
* ``shutdown()`` now closes the master server.
* Fixed master/slave replication on Python 3 (bytes handling, slave
  start-up, partial reads, clock replay on slaves).
* ``RotateFileWrapper.flush()`` works again.
* Writes no longer fail after ``start_master()`` (the master server now
  implements the full subscriber interface).
* ``validate_system`` skips methods whose source is unavailable (REPL,
  ``exec``) instead of crashing.
