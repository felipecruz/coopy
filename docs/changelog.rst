.. _changelog:

Changelog
=========

Unreleased
----------

* ``@transactional`` (``coopy.decorators``): a failed call leaves the domain
  as it was before the call, live and after a restart. The proxy deep-copies
  the domain's attributes before each call and restores them in place when the
  method raises; the failed call is not journaled or replicated. With
  ``durability="sync"``, a record that fails before it is complete on disk is
  truncated off the journal and the call is rolled back too
  (``PersistenceError.record_discarded``). Each call costs a copy of the whole
  state; it cannot be combined with ``@readonly`` or ``@unlocked``. Other
  methods behave as before. See :doc:`method_decorators`.

* ``@unlocked`` methods can use ``self._clock`` and ``self._env``: each proxy
  call now records into its own clock held in a context variable, so
  overlapping unlocked calls no longer append to each other's recording (or
  remove each other's ``_env``) and replay returns every action its own
  values. The domain object keeps a shared ``_clock`` that dispatches to the
  running call; outside a call it reads the system clock without recording.
  Snapshots still store a plain ``RecordClock``, so their format is unchanged.
  Reading ``obj._clock.results`` after a call no longer works; use the
  journaled action's ``results``.
* Validation resolves the method module's imports, so aliased
  (``from datetime import datetime as dt; dt.now()``) and module-qualified
  (``datetime.datetime.now()``) calls are recognised, and it now also covers
  ``time.time()``/``monotonic()``/``perf_counter()``, ``random.*``,
  ``uuid.uuid1()``/``uuid4()``, ``os.urandom()`` and ``secrets.*``, naming the
  ``self._clock``/``self._env`` replacement and the file and line. Open with
  ``validation="strict"`` to reject every such call, ``"off"`` to skip the
  check, or the default ``"warn"``, which logs them and, as before, rejects
  only ``datetime.now()``/``date.today()`` written that way. Rejections raise
  ``coopy.error.NonDeterministicCallError``, a ``PrevalentError``; the
  validator no longer raises a plain ``Exception`` internally. The old
  warning for any ``x.y.now()`` call is replaced by the resolved check.
* Recorded environment: domain methods get ``self._env`` (typed by the new
  ``coopy.Env`` protocol) with ``random()``, ``uniform()``, ``randint()``,
  ``choice()``, ``shuffle()``, ``sample()``, ``uuid4()``, ``token_bytes()``,
  ``token_hex()`` and ``token_urlsafe()``. Values are journaled in the clock's
  ``(method, value)`` record and replay after restarts and on replicas;
  divergent calls raise ``coopy.ClockDivergenceError``. ``choice``,
  ``shuffle`` and ``sample`` record positions, so replay returns the domain's
  own objects. Recorded tokens are stored in the journal; messages and
  ``python -m coopy log`` redact them. ``coopy.testing.SeededEnv`` and
  ``install_env`` make values reproducible in tests. See :doc:`use_env`.
* Journals record which clock call produced each value: actions are stored
  with ``record_version`` 2 and ``results`` as ``(method, value)`` pairs, and
  the on-disk format (``coopy.json``) moves to version 2. Replay now detects
  ``now()``/``utcnow()`` or ``time()``/``monotonic()`` swapped and ``now(tz)``
  with a different offset, and ``ClockDivergenceError.expected`` names the
  recorded call. Older bare-value journals replay unchanged. A format 1
  directory gains the format 2 manifest on its next writable open, after which
  older coopy releases refuse it with ``FormatError`` before decoding.
  ``python -m coopy log`` prints clock values as ``method=value``. See
  :doc:`use_clock`.
* Clock sources: ``self._clock.now(tz=None)`` mirrors ``datetime.now(tz)``, so
  ``now(timezone.utc)`` records an aware value, and the new ``time()`` (epoch
  seconds) and ``monotonic()`` (durations inside a method) are recorded and
  replayed like the other clock calls. Aware values keep their offset through
  pickle and JSON storage and replication; existing naive journals replay
  unchanged. Replay raises ``coopy.ClockDivergenceError`` when ``now(tz)``
  finds a naive value or ``time()``/``monotonic()`` finds no ``float``. The
  ``coopy.Clock`` protocol and the ``coopy.testing`` clocks gain the new
  methods; ``RecordClock`` still calls a source's ``now()`` without arguments
  when no ``tz`` is passed. The clock guide now recommends aware UTC. See
  :doc:`use_clock`.
* ``coopy.testing``: ``FrozenClock(dt)`` and ``ManualClock(start)`` (with
  ``advance(timedelta)`` and ``set(dt)``) implement ``coopy.Clock``, and
  ``install_clock(system, clock)`` makes an opened system's ``self._clock``
  read from a test clock while still journaling the values. ``RecordClock``
  accepts an optional ``source`` clock. ``coopy.tests.utils.TestClock`` and
  ``TestSystemMixin`` are deprecated (removal: v0.9); ``mock_clock`` and
  ``enable_clock`` now also work on opened systems. See :doc:`util_api`.
* ``coopy.Clock``: a typed protocol for the injected ``self._clock`` with
  ``now()``/``utcnow()`` returning ``datetime`` and ``today()`` returning
  ``date``. Both ``RecordClock`` and the replaying ``RestoreClock`` implement
  it; annotate domains with ``_clock: coopy.Clock``. ``RecordClock`` no longer
  has a ``__getattr__`` fallback, so type checkers reject unknown clock
  methods. ``_clock: RecordClock`` annotations keep type-checking.
* Replay detects clock divergence: a replayed method that calls ``today()``
  where ``now()``/``utcnow()`` was recorded (or the reverse), receives a value
  of the wrong type, or makes more or fewer clock calls than were recorded now
  raises ``coopy.ClockDivergenceError`` naming the action, the zero-based clock
  call index and the expected and actual call. Strict recovery reports it as a
  ``clock`` stop, salvage stops at that record, and replicas become
  unsynchronized with the same message. Previously ``today()`` silently
  received a ``datetime``, extra calls raised a bare ``IndexError`` and unused
  values were ignored.
* ``python -m coopy`` command-line tool: ``inspect``, ``verify``, ``log``,
  ``snapshot``, ``prune`` and ``convert`` for data directories. Every command
  holds the writer lock and exits non-zero on errors. See :doc:`cli`.
* ``coopy.control(system).prune(keep=N, keep_for=None)`` and
  ``coopy.prune(directory, keep=N)`` delete checkpoints older than the newest
  ``N`` (and outside ``keep_for``) together with the journals only they need.
  The current checkpoint and its journals are never removed; pruning holds the
  domain lock or, for a closed directory, the writer lock. See :doc:`snapshots`.
* Integrity key rotation: ``secret`` may be a list of accepted keys, newest
  first. Signed storage verifies with any listed key and new records are
  signed with the first; ``coopy.convert(..., new_secret=new_key)`` re-signs a
  directory so old keys can be retired. See :doc:`usage`.
* ``coopy.convert(src, dst, ...)`` copies a closed data directory into a new
  or empty one with another serializer (``new_serializer``), signing setting
  (``new_secret``) or snapshot compression. The source is recovered strictly
  and never written; the destination receives one fresh checkpoint and is
  removed again if anything fails. See :doc:`modern-api`.
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
