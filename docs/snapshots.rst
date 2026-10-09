.. _snapshots:

Snapshots
=========

Motivation
----------

If your domain is really active and generates tons of logs, we suggest you to take snapshots from your domain periodically. A snapshot allows you to delete your logs older then it's timestamp and make the restore process faster.
Today, while taking a snapshot the domain is *locked*. It's fairly common setup a local slave just for taking snapshots.

Example
-------

Example::

    from coopy.base import init_persistent_system

    persistent_todo_list = init_persistent_system(Todo())
    persistent_todo_list.add_task("Some Task Name", "A Task Description")

    # Take snapshot
    persistent_todo_list.take_snapshot()


API
---

For domain instances

.. function:: domain.take_snapshot()
    Takes the domain snapshot.



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
Power-loss durability, corruption recovery, and mutations that bypass the proxy
lock (including ``@unlocked`` methods) are outside this checkpoint guarantee.
