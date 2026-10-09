.. _replication:

Master/slave replication
============================

.. warning::

   Replication is experimental and **incomplete until roadmap F13 is accepted**.
   F5 supplied bootstrap and catch-up code, described below, but F13 remains
   open. This example demonstrates the current API, not a production recovery
   or failover guarantee.

A new slave receives a snapshot of the populated master, then replays the
ordered actions queued during transfer. Snapshot capture holds the same lock as
proxy mutations. Socket writes happen outside that lock, so a slow transfer
does not hold up domain writes. Live updates continue in the same packet queue.

Experimental local example
------------------------------

This runnable example uses the tutorial's ``wiki.py`` alongside
``replication.py``. Run it only on a trusted host/network; the master listener
binds the host's resolved address, falling back to loopback if resolution
fails. It uses an OS-selected port and closes both endpoints.

.. literalinclude:: examples/replication.py
   :language: python

``init_persistent_system`` supplies the master's local persistence.
``init_system(Wiki(), [])`` creates an ephemeral slave with no local journal
or snapshot manager; it is not a durable restart recipe. Use readonly domain
queries after waiting for synchronization.

Readiness and failures
--------------------------

``start_slave`` returns immediately after connecting and starting its receiver.
``connection.synchronized`` becomes true only after the snapshot and every
queued action preceding the master's catch-up marker have been applied. This
is a point-in-time boundary; subsequent replication is asynchronous. A wait
timeout does not cancel the connection; call ``close`` to stop waiting entirely.

The bootstrap object remains private until that marker. Proxy reads and
snapshots reject access while unsynchronized, and domain writes are forbidden
on a slave. The receiver uses the proxy lock so reads cannot race action replay
or replacement of the bootstrap object. Do not access ``replica.obj`` directly
or use ``@unlocked`` queries to bypass these protections.

Authentication rejection, incomplete packets, disconnects, malformed bootstrap,
and detected replay divergence clear synchronization. ``connection.error``
records the receiver failure. A failed or disconnected slave must reconnect and
bootstrap again; it is never automatically promoted. Closing a proxy stops its
receiver; ``master.shutdown()`` stops its listener and disconnects its slaves.

Protocol and limits
-----------------------

Upgrade master and slaves together. Authentication now sends a four-byte
network-order password length followed by the password (up to 4096 bytes),
allowing fragmented TCP delivery and passwords longer than the old 20-byte
read. This handshake and the explicit ready marker are incompatible with old
peers. Snapshot/action payloads remain compressed pickles.

Use only trusted peers on a trusted network: passwords are unencrypted and
pickle loading executes code. Bootstrap and pending action queues are held in
memory. Queues have no byte limit; a persistently slow slave can consume master
memory and should be disconnected by the operator. Serializing a large domain
still pauses master mutations, even though transferring it does not.

Only calls published by the proxy are replicated. Successful non-readonly
``@abort_exception`` calls are published; failing ones are omitted without
rolling back mutations already made on the master. Direct mutations are not
published either. These changes may enter a later bootstrap snapshot but are
not sent as live actions. Recorded clock values are replayed; other domain
behavior must be deterministic. This is not durable slave journaling, automatic
reconnect, automatic failover, or a synchronous replication acknowledgment.
