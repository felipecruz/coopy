.. _replication:

Master/slave replication
============================

.. warning::

   Replication is experimental and requires trusted peers. Bootstrap and
   ordered catch-up are tested, including writes during transfer; this is not
   a production recovery or failover guarantee.

A new slave receives a snapshot of the populated master, then replays the
ordered actions queued during transfer. Snapshot capture holds the same lock as
proxy mutations. Socket writes happen outside that lock, so a slow transfer
does not hold up domain writes. Live updates continue in the same packet queue.

Experimental local example
------------------------------

This runnable example uses the tutorial's ``wiki.py`` alongside
``replication.py``. Run it only on a trusted host/network. By default the
master listens on loopback (``127.0.0.1``) only; to accept slaves from other
machines pass an interface address, for example
``start_master(host="0.0.0.0")``, and only do so on a trusted network. The
example uses an OS-selected port and closes both endpoints.

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

``replica.shutdown()`` retains the slave role and its unsynchronized read/write
guard, including when shutdown interrupts bootstrap. Connection setup failures
also retain that guard and record ``connection.error`` on ``replica.slave``;
``start_slave`` still raises the connection exception. To reconnect explicitly,
stop the previous receiver with ``replica.shutdown()``, then call
``replica.start_slave(...)`` and wait for a fresh bootstrap. Starting a second
active receiver or converting a slave to a master raises ``RuntimeError``.

Protocol and limits
-----------------------

Upgrade master and slaves together. Authentication now sends a four-byte
network-order password length followed by the password (up to 4096 bytes),
allowing fragmented TCP delivery and passwords longer than the old 20-byte
read. This handshake and the explicit ready marker are incompatible with old
peers. Snapshot/action payloads remain compressed pickles.

Passwords are compared with ``hmac.compare_digest`` to avoid content-dependent
comparison timing, but are still transmitted in plain text. This shared-password
handshake remains a stopgap pending the encrypted transport proposed in
``FUTURE.md`` §2.2 (pyzmq). Neither passwords nor snapshot/action payloads are
encrypted by the current transport. Use only trusted peers on a trusted network:
pickle loading executes code.

The current backend uses ``select``. The empty ``linux_epoll.py`` and
``osx_kqueue.py`` placeholders have been removed; if platform-specific polling
is needed, use standard-library ``selectors`` or the future pyzmq transport
instead of adding per-platform backends.

Bootstrap and pending action queues are held in memory. Queues have no byte
limit; a persistently slow slave can consume master
memory and should be disconnected by the operator. Serializing a large domain
still pauses master mutations, even though transferring it does not.

Only calls published by the proxy are replicated. Successful non-readonly
``@abort_exception`` calls are published; failing ones are omitted without
rolling back mutations already made on the master. Failed ``@transactional``
calls are rolled back on the master and are not published either. Direct mutations are not
published either. These changes may enter a later bootstrap snapshot but are
not sent as live actions. Recorded clock values are replayed; other domain
behavior must be deterministic. This is not durable slave journaling, automatic
reconnect, automatic failover, or a synchronous replication acknowledgment.
