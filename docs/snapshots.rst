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

Snapshots are written and synced to a temporary file in the data directory,
then published with an atomic rename. A serialization, write, or publication
failure leaves the previous checkpoint and its journals available. Manual
snapshot failures propagate to the caller; the timer logs failures and retries
at its next interval. An interrupted snapshot may leave a hidden
``.coopy-snapshot-*`` file; recovery ignores it. Remove such files only while the
system is stopped.

Existing numbered snapshot and journal formats retain their interpretation.
This cannot repair an old checkpoint whose earlier-numbered journal already
contains ambiguous post-snapshot writes. Back up existing data before upgrading.
Power-loss durability, corruption recovery, and mutations that bypass the proxy
lock (including ``@unlocked`` methods) are outside this checkpoint guarantee.
