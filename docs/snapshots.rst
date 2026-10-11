.. _snapshots:

Snapshots
=========

Taking checkpoints
------------------

Snapshots reduce recovery replay by storing the current domain state. Use
``proxy.take_snapshot()`` for a manual checkpoint. To schedule checkpoints,
call ``proxy.start_snapshot_manager(seconds)`` once; the first attempt occurs
after that interval. ``proxy.close()`` stops and joins the timer. Stop
application writers before closing. Close does not take a final snapshot.

The :doc:`tutorial` contains a runnable example with manual checkpoints, timer
setup/cleanup, and close/reopen recovery. Snapshot serialization holds the
domain lock and can pause writes. Replication supports consistent bootstrap
but does not provide durable slave restart; do not depend on a slave as a
durable snapshot service.

Retain the full directory until you have verified a stopped-system backup and
restore. There is no automatic pruning. File numbers, not timestamps, determine
which journals are required. Never delete later-numbered journals needed by
the checkpoint you intend to recover.

Checkpoint recovery
-------------------

Default manual and timed snapshots hold the proxy's domain lock while serializing state
and advancing the journal. New actions go into a journal numbered after the new
snapshot, so reopening replays them exactly once. Reopening starts a new journal
rather than appending a new pickle memo to an existing stream. Size rotation
happens between complete action records.

The boundary is the snapshot's file number, not its timestamp. For a snapshot
numbered N, every action already in that snapshot belongs to an earlier journal;
the active journal is rotated to a number greater than N before the snapshot is
published. The domain lock remains held through publication, so a concurrent
method call cannot write into the gap. Recovery loads the latest snapshot and
only journals with numbers strictly greater than N. Old journals are retained.
Repeated snapshots, timer snapshots, and new writes after reopening follow the
same rule. Use the proxy's ``take_snapshot()`` for a running persistent system;
the low-level ``SnapshotManager`` alone does not coordinate its journal or lock.

Snapshots are written, flushed, synced, and closed in a temporary file in the
data directory, then published with an atomic rename. A serialization, write,
flush, close, journal-rotation, or publication
failure leaves the previous checkpoint and its journals available. Manual
snapshot failures propagate to the caller; the timer logs failures and retries
at its next interval. Temporary-file cleanup is best effort: a cleanup failure
is logged without replacing the original snapshot error. An interruption or
cleanup failure may leave a hidden ``.coopy-snapshot-*`` file; recovery ignores
it, even if it contains a complete pickle. Remove such files only while the
system is stopped. Keep the previous checkpoint and all later-numbered journals
after a failed snapshot; journal rotation alone does not publish a checkpoint.

Existing numbered snapshot and journal formats retain their interpretation.
This cannot repair an old checkpoint whose earlier-numbered journal already
contains ambiguous post-snapshot writes. Back up existing data before upgrading.
Journals numbered at or below the latest snapshot remain excluded, including
any ambiguous tail; replaying them in full would duplicate checkpointed actions.
Legacy protocol-2 streams retain their per-file pickle memo behavior. Rotation
starts a fresh memo: aliases within a record are preserved, but object identity
across separate journal files or between a snapshot and later arguments is not
guaranteed. Pass stable identifiers to refer to existing domain objects.
With ``durability="sync"``, checkpoint publication also syncs the data directory.
A directory-sync failure after rename can leave the complete new checkpoint
visible despite an exception; old checkpoints and journals remain available.
See :doc:`usage` for synchronous acknowledgments, strict recovery, and salvage.
Mutations that bypass the proxy lock (including ``@unlocked`` methods) remain
outside this checkpoint guarantee.

Pruning old checkpoints
-----------------------

Every checkpoint and journal is kept until you prune. Recovery reads only the
newest checkpoint and the journals numbered after it; older files are history
for manual fallback. ``coopy.control(system).prune(keep=N)`` deletes all but the
newest ``N`` checkpoints together with the journals numbered before the oldest
kept one, so every kept checkpoint can still replay to the current state::

    report = coopy.control(proxy).prune(keep=3, keep_for=timedelta(days=7))
    print(report.snapshots, report.journals)

``keep_for`` additionally keeps every checkpoint published (file modification
time) within that period; a checkpoint is deleted only when it is outside both.
``keep`` must be at least 1, so the current checkpoint and its journals are
never removed. Pruning runs under the domain lock: writes and blocking
snapshots wait for it, and a fork snapshot publishing concurrently only adds a
newer checkpoint. Files are deleted oldest first and the directory is synced,
so an interruption leaves a shorter but contiguous history. Signed directories
stay verifiable because remaining records are never rewritten.

``coopy.prune(directory, keep=N)`` prunes a closed directory while holding its
writer lock (``LockError`` while a writer has it open). Hidden
``.coopy-snapshot-*`` temporary files are not touched.

Optional compression
--------------------

Install ``pip install 'coopy[zstd]'`` or ``pip install 'coopy[lz4]'`` and open
with ``snapshot_compression="zstd"`` or ``snapshot_compression="lz4"``.
This changes newly written snapshots only. A versioned envelope identifies the
compression; recovery automatically reads both old uncompressed and compressed
snapshots, but requires the corresponding extra for compressed data. It never
guesses the serializer: reopen with the same compatible serializer and secret.
With HMAC enabled, the compressed envelope is authenticated before any
decompression or deserialization. Compression adds checksums but is not a
replacement for authentication. Both pickle and registered JSON are supported.

Compressed and signed snapshots currently construct whole payloads in memory;
allow memory for serialized, compressed, and decoded copies. There is no
decompressed-size cap. Compression ratio and performance depend on the data.
Keep extras installed wherever recovery or salvage may be needed.

Opt-in fork snapshots
---------------------

On supported POSIX systems, a single-threaded application can explicitly assert
that its state and serializer are fork-safe::

    job = coopy.control(proxy).take_snapshot(mode="fork", fork_safe=True)
    # The parent can now handle more requests and proxy mutations.
    proxy.add("after the checkpoint boundary")
    if job is not None:
        job.wait(timeout=60)

The lock protects journal synchronization, reserving the snapshot number,
rotating the journal past it, and ``fork()``. The child serializes the copy-on-write
view into a preopened hidden file, including compression/signing when enabled,
flushes that file, and calls ``os._exit``. It never publishes a checkpoint,
executes journal actions, starts workers, logs errors, or runs normal exit
handlers. The parent alone reaps it, syncs its file, renames it, and (in sync
mode) syncs the directory. Parent writes after fork use the later journal,
whether the child succeeds or fails. Old checkpoints and journals are retained.

``wait()`` returns only after publication and is idempotent; failures are also
remembered. A timeout kills and reaps the child, removes its hidden file when
possible, and raises ``TimeoutError``. Child serialization failures raise
``PersistenceError`` without serializing the child's exception. Parent I/O errors
propagate. A directory-sync failure after rename can leave a complete visible
checkpoint. Call ``wait()`` before taking another snapshot; overlapping
checkpoints are rejected. ``close()`` waits up to 60 seconds for an outstanding
job and propagates its error while still closing resources. Do not reap the
child yourself or install a SIGCHLD handler that does so. A parent crash can
leave a hidden file or an orphan child; recovery ignores hidden files.

Fork mode requires all of the following:

* POSIX ``os.fork`` outside macOS, called from the sole Python main thread.
  macOS always falls back because higher-level system APIs can make fork unsafe.
* No replication role and no snapshot timer or other live Python thread at fork.
  Timed snapshots remain blocking. Threads created after fork do not enter the
  child; do not race thread creation with the eligibility check and fork.
* An explicit ``fork_safe=True`` application assertion: no hidden native threads,
  unsafe at-fork handlers, inherited locks/resources needed by serialization,
  or serializer/reducer/finalizer callbacks with external effects. Coopy cannot
  detect these properties. Arbitrary ``__getstate__``, ``__reduce__``, registered
  codecs and C extensions are not automatically safe. Use blocking snapshots
  if you cannot establish these conditions. Copy-on-write does not isolate
  external resources or shared memory.

Use ordinary CPython builds; embedded and free-threaded runtimes have not been
validated. Unrelated open descriptors remain inherited until the child exits;
the application must tolerate that temporary retention.

If these detectable conditions fail, or the assertion is absent, coopy emits
``RuntimeWarning``, takes a blocking snapshot, and returns ``None``. A fork
system-call failure propagates; it does not silently retry serialization.
See Python's `os.fork restrictions <https://docs.python.org/3/library/os.html#os.fork>`_.
Python execution after fork in a multithreaded process is not supported.
The eligibility check cannot establish native-library or user-callback safety.
Fork avoids serializing under the parent's lock but still pauses for journal
synchronization, page-table copying and fork handlers, and copy-on-write pages
can increase memory pressure. No bounded pause or throughput is promised.

.. toctree::
   :maxdepth: 1

   performance
