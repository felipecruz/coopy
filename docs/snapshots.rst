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



