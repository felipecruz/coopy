.. _client_server:

Client-server integration
=========================

An application can expose a coopy domain through an RPC or HTTP server. The
server should own the persistent proxy and its data directory, route mutations
through proxy methods, and close the proxy during orderly shutdown.

Use ``coopy.base.init_persistent_system`` as in :doc:`tutorial`. Return detached
query results, validate input at the application boundary, and coordinate
external effects outside replayed methods. The proxy lock only serializes calls
that respect it; it does not make arbitrary application code thread-safe.

The historical Pyro example used obsolete APIs and is no longer maintained.
No RPC framework integration is currently tested here. Network replication is
a separate, experimental feature; see :doc:`replication` for its limitations.
