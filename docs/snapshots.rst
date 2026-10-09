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
domain lock and can pause writes. Replication remains incomplete pending F13;
do not depend on a slave as a durable snapshot service.

Retain the full directory until you have verified a stopped-system backup and
restore. There is no automatic pruning. File numbers, not timestamps, determine
which journals are required. Never delete later-numbered journals needed by
the checkpoint you intend to recover.

Checkpoint recovery
-------------------

Manual and timed snapshots hold the proxy's domain lock while serializing state
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
