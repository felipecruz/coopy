.. _usage:

Persistence and recovery guide
==================================

Opening and closing a system
--------------------------------

Use ``from coopy.base import init_persistent_system`` and call
``init_persistent_system(obj, basedir=None)``. ``obj`` is an instance or a class
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
proxy. Replication is experimental and incomplete pending F13; see
:doc:`replication` for the existing lifecycle API.

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
#. Inspect ``coopy.log`` and verify application invariants before serving users.
   Current recovery logs several decoding and replay failures and continues;
   ``EOFError`` is treated as end-of-file even for a truncated record. Some
   divergence is not detected. A returned proxy is not proof of complete
   recovery. Strict recovery and explicit salvage reporting remain F11 work.

Keep the full directory until a backup and restore have been verified. There is
no automatic retention policy. Consult :doc:`snapshots` for checkpoint failure
handling, old-format boundaries, and ignored temporary files.

Current durability contract
-------------------------------

A normal successful mutation executes in memory before its action is appended.
Journal writes flush Python buffers to the operating system, but normal action
completion and ``close()`` do not call ``fsync``. A serialization or I/O failure
can therefore leave changed memory despite an exception, with no rollback.
Normal calls may also trigger size rotation, which syncs the old journal; this
is not a per-call synchronous durability policy.

Clean close/reopen recovery is supported for deterministic, journaled calls
with intact storage. A process crash can interrupt a record; a power loss can
lose acknowledged writes. There is no synchronous commit guarantee (F12).
Snapshots sync a temporary file, advance the journal under the domain lock, and
atomically rename the checkpoint. The containing directory is not synced, so
this also does not establish a power-loss durability guarantee. Checkpoints
coordinate only mutations respecting the proxy lock. See :doc:`snapshots` for
the precise numbering and publication boundary.
