.. _replication:

Master/slave replication
=======================

A new slave receives a snapshot of the populated master, then replays the
ordered actions queued during transfer. Snapshot capture holds the same lock as
proxy mutations. Socket writes happen outside that lock, so a slow transfer
does not hold up domain writes. Live updates continue in the same packet queue.

Start a master with an existing proxy::

    from coopy.base import init_persistent_system

    master = init_persistent_system(Wiki, basedir="master-data")
    master.start_master(port=8012, password="shared-secret")

Start a read-only slave without a local persistence directory::

    from coopy.base import init_system

    replica = init_system(Wiki(), [])
    connection = replica.start_slave("master-host", 8012,
                                     password="shared-secret")
    if not connection.wait_until_synchronized(timeout=30):
        replica.close()
        raise RuntimeError(connection.error or "Bootstrap timed out")
    page = replica.get_page("Home")  # an @readonly domain method
    replica.close()

Readiness and failures
----------------------

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
-------------------

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

Only calls published by the proxy are replicated. Direct mutations and the
existing omission of successful ``@abort_exception`` calls are not repaired by
bootstrap. Recorded clock values are replayed; other domain behavior must be
deterministic. This is not durable slave journaling, automatic reconnect,
automatic failover, or a synchronous replication acknowledgment.
