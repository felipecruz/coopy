.. _usage:

Persistence and recovery guide
==================================

Opening and closing a system
--------------------------------

Use ``from coopy.base import init_persistent_system`` and call
``init_persistent_system(obj, basedir=None, recovery="strict",
durability="buffered")``. ``obj`` is an instance or a class
that can be constructed without arguments, even when reopening existing data.
A new directory gets an initial snapshot. Existing data replaces the supplied
object with the latest snapshot, then replays later journaled calls. See the
complete, runnable :doc:`tutorial`.

Pass ``basedir`` as a string. Its parent directory must exist; coopy creates
only the final directory. Without it, the lowercased class name is used relative
to the current working directory. Prefer an absolute path and keep the working
directory stable while a proxy is open. ``coopy.log`` is written in the current
working directory, separately from persistence files.

Use one owning process and one persistent proxy per data directory; there is
no interprocess writer lock. Stop application callers, then call ``close()`` in
``finally`` to stop the snapshot timer and close subscribers. There is no proxy
context manager. Do not reuse a closed proxy. Reopen with the same data path
and compatible, importable domain classes. ``close()`` does not take a snapshot.

``init_system(obj, subscribers)`` is a low-level proxy constructor in
``coopy.base``; it does not configure disk persistence. The old ``master``,
``replication``, and ``snapshot_time`` initializer keywords are not supported.
Use ``take_snapshot()`` or ``start_snapshot_manager(seconds)`` on the persistent
proxy. Replication is experimental; see :doc:`replication` for bootstrap,
readiness, and the lifecycle API.

What gets recorded
----------------------

An ordinary method call through the proxy runs under a reentrant lock, then
records its method name, arguments, recorded clock results, and failure outcome.
Calls on ``self`` inside the domain are part of that outer action; they do not
create separate proxy actions. The domain must be pickleable, and arguments
must be pickleable when journaled. Prefer immutable values and stable IDs over
passing references to existing domain objects.

``@readonly`` methods skip the journal. ``@abort_exception`` omits failed calls
but keeps successful ones; it does not roll back memory or external effects.
``@unlocked`` skips the proxy lock and puts concurrency correctness on the
application. Read :doc:`method_decorators` before combining these decorators.

Mutable-object escape paths
-------------------------------

The proxy does not recursively wrap objects. Reading ``wiki.pages``, accessing
``wiki.obj``, or returning a live list, dictionary, or object exposes mutable
state outside method interception. Mutating those references does not journal
an action or acquire the domain lock. Assigning attributes directly on the
proxy is not a persistent setter either. A readonly method can still mutate
state: its decorator is a promise made by the application.

Use mutation methods on the proxy and return immutable values or detached
copies from queries. A shallow copy protects only its outer container; copy
nested mutable values too. Do not mutate caller-owned objects retained by the
domain after passing them as arguments. Such changes can leak into snapshots
without a matching journal action, so live and recovered state can differ.

Deterministic replay and external effects
---------------------------------------------

Recovery runs domain methods again; it does not just assign their old results.
Use ``self._clock.now()``, ``utcnow()``, and ``today()`` inside domain methods to
replay the original time values. Capture randomness, environment-dependent
values, and external inputs before calling the proxy and pass immutable values
as arguments. Do not rely on network responses or current file contents during
replay. The clock validator is a limited source check, not a determinism proof.

Sending email, charging an account, or writing a file inside a journaled method
can happen again during recovery or replication. Keep external effects outside
replayed methods and use an application-level idempotency/reconciliation design
when coordinating them. Coopy offers neither an external transaction nor an
exactly-once side-effect guarantee. Code changes can also change replay results;
back up data and test recovery against compatible application versions.

Trusted storage and recovery procedure
------------------------------------------

Snapshots and journals contain Python pickles. Loading them can execute code.
Open only storage from trusted sources and protect write access to the data
directory and backups. Do not load a downloaded or user-supplied database to
inspect it. Replication also requires trusted peers and networks.

For a controlled restart:

#. Stop writers and close the proxy. Preserve the complete data directory as a
   backup before an upgrade or recovery experiment.
#. Reopen the directory with the same importable domain classes. Recovery picks
   the highest numbered snapshot and journals with strictly higher numbers.
   Keep their names and ordering intact; never concatenate pickle streams.
#. Open with ``recovery="strict"`` (the default). A detected decoding error,
   truncated record, missing method, or changed success/failure outcome raises
   ``coopy.restore.RecoveryError`` before a proxy or new journal is created.
   Inspect ``error.report`` for the checkpoint, replay count, and stopping
   position (file, byte offset, one-based record number, and method name).

For an explicit salvage inspection, use::

    result = init_persistent_system(Domain, basedir="data", recovery="salvage")
    print(result.report)
    recovered_domain = result.system

Salvage returns a ``RecoveryResult``, not a proxy, and does not create or modify
storage. It stops at the first defect across all journal files; later records
are never skipped into. ``report.replayed`` counts completed matching actions;
``expected_failures`` counts actions that raised both originally and on replay.
``report.stop`` describes the defect, or is ``None`` when EOF was reached cleanly.
A broken checkpoint returns ``system=None``; older checkpoints are not tried.
If a divergent method already ran, ``stop.state_may_be_changed`` is true:
inspection state can include that attempted action's mutations. There is no
rollback. Reconcile and export inspected state into a separate data directory
using application-specific tooling; do not serve it as a recovered live system.

A strict proxy exposes its ``recovery_report`` too. ``complete`` means replay
reached the end without a detected defect, not that determinism was proven.
``legacy_actions`` identifies records with missing/None outcome metadata. Their
successful replay is allowed but unverified; an exception stops recovery.
Current records store only a success/failure boolean: an expected exception is
consumed during replay, but its type/message and return values cannot be
compared. Original application exceptions still reach callers of live methods.
Unframed, unsigned pickle storage cannot detect all corruption, removed whole
records, or changed outcomes that still have the same success/failure status.
Strict mode does not make untrusted pickle storage safe. Replay itself can
repeat external effects even when recovery ultimately raises.

Keep the full directory until a backup and restore have been verified. There is
no automatic retention policy. Consult :doc:`snapshots` for checkpoint failure
handling, old-format boundaries, and ignored temporary files.

Durability policies
-------------------

``durability="buffered"`` is the default. Journal writes flush Python buffers
to the operating system. Normal action completion and ``close()`` do not call
``fsync``; size rotation still syncs the old journal. A power loss can lose
acknowledged buffered calls.

Choose ``durability="sync"`` when opening each persistent proxy::

    proxy = init_persistent_system(Domain, basedir="data", durability="sync")

A journaled mutation executes in memory, serializes a complete record, flushes
it, and calls ``os.fsync`` on the journal before returning its result (or
re-raising its original domain exception). Readonly calls and omitted failed
``@abort_exception`` calls do not sync a journal record. The policy is selected
on each open, not stored in the pickle format; it does not retroactively
validate earlier buffered acknowledgments.

Synchronous mode also syncs the data directory on journal creation, rotation,
and checkpoint publication, and its existing parent if coopy creates the data
directory. Snapshots retain the locked checkpoint boundary and file sync in
both modes. ``close()`` in synchronous mode flushes and syncs before closing;
errors propagate and the file is still closed. Stop writers before closing.
POSIX directory-sync support is required; unsupported operations fail rather
than silently downgrade. This contract is completion of ``os.fsync``, subject
to the OS/filesystem/device guarantees. It does not promise hardware cache
flush beyond that API, protect against disk damage, or validate actual power
loss. Keep backups and use a durable existing parent directory.

A serialization, short write, write, flush, sync, or action-triggered rotation
failure raises ``coopy.journal.PersistenceError`` with the underlying cause in
``__cause__``. **Memory may already be changed; there is no rollback.** A record
may be absent, partial, or fully persisted despite the exception. A persistence
error takes precedence over a simultaneous domain exception. The journal
refuses subsequent mutations and checkpoints through that proxy; readonly
inspection remains available. Stop callers, close the proxy (handling close
errors), preserve storage, and inspect strict recovery or explicit salvage.
Do not blindly retry the mutation: it may already be in the journal.

A synchronous checkpoint's directory sync can fail after its atomic rename;
the complete new checkpoint may then be visible although ``take_snapshot()``
raised. The prior checkpoint and journals are retained. Initialization and
snapshot failures propagate too; these calls must not be assumed to have
completed just because a file exists.

Clean restart recovery requires deterministic, journaled calls and intact
storage. A process crash can interrupt an unacknowledged record; strict
recovery detects incomplete records. Calls bypassing the proxy lock, including
``@unlocked`` mutations, are outside the concurrency and checkpoint contract.
See :doc:`snapshots` for the precise numbering and publication boundary.
