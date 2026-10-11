.. _usage:

Persistence and recovery guide
==================================

Opening and closing a system
--------------------------------

Use ``from coopy.base import init_persistent_system`` and call
``init_persistent_system(obj, basedir=None, recovery="strict",
durability="buffered", secret=None)``. ``obj`` is an instance or a class
that can be constructed without arguments, even when reopening existing data.
A new directory gets an initial snapshot. Existing data replaces the supplied
object with the latest snapshot, then replays later journaled calls. See the
complete, runnable :doc:`tutorial`.

Pass ``basedir`` as a string. Its parent directory must exist; coopy creates
only the final directory. Without it, the lowercased class name is used relative
to the current working directory. Prefer an absolute path and keep the working
directory stable while a proxy is open. ``coopy.log`` is written in the current
working directory, separately from persistence files.

Use one owning process and one persistent proxy per data directory. A writable
open takes an exclusive lock on ``coopy.lock`` in the data directory
(``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows) and holds it until
``close()``, context-manager exit or process exit, including a killed process.
Opening the same directory again for writing, from the same or another process,
raises ``coopy.error.LockError``, a ``LifecycleError`` naming the directory and,
where available, the holder's PID. ``recovery="salvage"`` is read-only and does
not take the lock, so it can inspect a directory while a writer runs. The lock
is advisory: network filesystems such as NFS or SMB may not honor it, so keep
data directories on local storage. Leave ``coopy.lock`` in place; it is reused
on the next open.

Each data directory carries a manifest, ``coopy.json``, recording the on-disk
``format_version``, the ``serializer`` name, whether storage is HMAC-``signed``
and the ``coopy_version`` that wrote it. A writable open creates it, under the
directory lock, when the directory is new; a directory without one (written by
coopy 0.5 or earlier) is read as legacy format 0 and gains a manifest on its
next successful writable open. Salvage never writes it. Every open, including
salvage and ``coopy.restore.restore``, checks the manifest before decoding
anything: a newer ``format_version`` than the running library supports, an
unreadable manifest, a different serializer, or a secret given for unsigned
storage (or missing for signed storage) raises ``coopy.error.FormatError``
naming the directory and the mismatch. Do not edit the manifest by hand.

Stop application callers, then call ``close()`` in
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
Use ``self._clock.now(timezone.utc)``, ``now()``, ``utcnow()``, ``today()``,
``time()`` and ``monotonic()`` inside domain methods to replay the original time
values. Capture randomness, environment-dependent
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
   truncated record, missing method, changed success/failure outcome, or
   clock divergence (``coopy.ClockDivergenceError``, see :doc:`use_clock`) raises
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

Authenticated storage (opt-in)
------------------------------

Pass a nonempty ``bytes`` secret on every open to enable HMAC-SHA256 integrity::

    from pathlib import Path
    secret = Path("/run/secrets/coopy-storage-key").read_bytes()
    proxy = init_persistent_system(Domain, basedir="signed-data", secret=secret)

Generate a high-entropy key once (for example, ``secrets.token_bytes(32)``),
store it **outside the data directory**, and supply the same bytes after each
restart. Do not embed it in the domain object, source control, logs, or a backup
of the data directory. Keep a separate secure key backup; losing the key makes
signed storage unrecoverable. **This detects tampering; it does not encrypt
any data.** Anyone who can read the directory can still read serialized data.
Anyone with the key can forge records. Application code and replication peers
must still be trusted; this option does not authenticate network replication.

New signed directories contain a random system identity in
``.coopy-integrity`` and versioned binary envelopes around each snapshot and
journal record. HMAC binds the payload and length to the identity, file name,
and record offset. A snapshot from another independently initialized system
is rejected even if both use the same secret. Back up the identity with all
numbered storage files, including when moving a directory to another path.
Never rename numbered files. The secret itself is never added to storage.

Recovery authenticates the selected snapshot and every later journal record
before constructing any unpickler or replaying any domain method. It retains
these exact bytes in memory so changing disk files after verification cannot
substitute unverified input. Wrong secrets, missing/invalid tags, unsigned
input, malformed envelopes, and incomplete records stop strict recovery with
``RecoveryError`` and ``report.stop.kind == "verification"``. The report gives
the offending file, offset, and record (zero for the checkpoint or identity).
``recovery="salvage", secret=secret`` also verifies everything first: on a
verification failure it returns ``system=None`` and the report without writing
storage or unpickling a partial prefix. It never bypasses authentication.
Obsolete files excluded by the checkpoint boundary are not verified.

Without a secret the existing unsigned format and recovery behavior remain
unchanged. There is no automatic signing of legacy directories or downgrade:
supplying a secret for unsigned storage fails. To migrate,
recover a trusted unsigned backup in a controlled environment with
``coopy.convert(src, dst, new_secret=secret)``, which writes a separate new
signed directory (``new_secret=None`` converts signed storage back to unsigned;
see :doc:`modern-api`).
Use the same secret for all writers and reopen operations on signed storage.

Key rotation
~~~~~~~~~~~~

``secret`` also accepts a nonempty list (or tuple) of keys, newest first. The
identity and every snapshot and journal record verify with any listed key; all
new records, snapshots and identities are signed with the first one. To rotate
from key ``A`` to key ``B``:

1. Reopen with ``secret=[B, A]``. Existing storage still verifies with ``A``,
   and everything written from now on is signed with ``B``.
2. Re-sign: with the system closed, run
   ``coopy.convert("data", "data-b", secret=[B, A], new_secret=B)``. The new
   directory has a fresh identity and one checkpoint, all signed with ``B``.
3. Verify ``data-b`` opens with ``secret=B``, keep ``data`` as a backup, swap
   the directories, and retire ``A``.

Until step 2 the directory still depends on ``A``: its identity and older
records are signed with it, so opening with ``secret=B`` alone fails
verification. A wrong or retired key fails verification before anything is
decoded, exactly like a wrong single secret. Every listed key is trusted to
forge records, so drop retired keys from the list as soon as re-signing is done.
Each signed journal record uses its own pickle memo; aliases within a record
survive, but cross-record object identity is not preserved. Use stable IDs.

HMAC does not prove freshness or completeness. A valid old directory (including
its identity) can be replayed, and deletion of whole files or complete trailing
records may be undetectable. Protect access and retain backups; detecting these
cases requires a trusted external checkpoint/counter. Removal of all storage
is indistinguishable from creating a new system. Restoring signed data uses
extra memory proportional to the selected snapshot and all journals needed
for replay; take regular checkpoints to bound that cost. Signed serialization
also buffers one complete snapshot or action. Durability still depends on the
policy below. An interrupted first initialization can leave an identity with
no checkpoint: preserve it for inspection and initialize a separate empty
directory rather than treating incomplete signed storage as a fresh system.

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

Enable group commit for concurrent synchronous calls with ``group_commit_delay=0.001``
(seconds). This lets a batch leader release the domain lock briefly while other
callers execute and append complete records. It then reacquires the lock and
syncs the batch. Every caller waits for its own record's batch, including
callers whose domain method raised a journaled exception. A batch sync or
rotation failure fails all its waiting calls and disables later writes.
Checkpoints and close drain pending batches. Completion order between callers
may differ from execution order; replay retains execution order.

The default, ``group_commit_delay=0``, retains immediate per-call synchronization.
A positive window adds latency to isolated writes and can reduce throughput on fast
storage. Benchmark your concurrency and storage before tuning it. Grouping
starts no worker thread. With grouping enabled, mutating ``@unlocked`` methods
also acquire the domain lock; readonly unlocked methods keep their behavior.
Reads can observe mutations whose callers are still waiting for sync; this
is not transaction isolation. Replication delivery does not imply a disk
acknowledgment. See :doc:`performance` for measured trade-offs.

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
