# Replication upgrade

Upgrade masters and slaves together. The new length-prefixed authentication and catch-up marker are incompatible with old peers.

Wait for bootstrap before reading:

```python
connection = replica.start_slave(host, port, password="shared-secret")
if not connection.wait_until_synchronized(timeout=30):
    replica.close()
    raise RuntimeError(connection.error or "Bootstrap timed out")
```

A timeout does not cancel bootstrap. Close the replica when abandoning the attempt. Disconnects clear `connection.synchronized`; reconnect and bootstrap before serving reads again. Replication remains asynchronous after initial catch-up.

# Recovery and operational limits

- Back up existing data before upgrading. The fix prevents new checkpoint-boundary losses; it cannot infer ambiguous writes already hidden behind older broken checkpoints.
- Interrupted snapshots may leave ignored `.coopy-snapshot-*` files. Remove them only while the system is stopped.
- Use proxy methods and the proxy lock. Direct mutations and `@unlocked` methods bypass consistency protection; successful `@abort_exception` calls remain unpublished pending F8.
- Use only trusted replication peers and storage. Pickles execute code, and the network password is unencrypted.
- Monitor slow replicas: pending action queues are unbounded in memory. Disconnect replicas that cannot keep up.
- Power-loss durability, corruption recovery, durable slave restart, and automatic failover remain outside these changes.

# Validation

All 83 tests passed on local Python 3.12.2, including restart/failure recovery and TCP/Unix replication. The supported Python/OS CI matrix still needs to run. ROADMAP.md records the exact implementation commits and follow-up work.
