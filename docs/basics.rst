Persistence model
=================

Coopy keeps the domain object graph in memory. A proxy intercepts method calls
and records non-readonly actions in numbered pickle journals. Recovery loads
the latest numbered snapshot, then re-executes actions from journals numbered
strictly after that snapshot. A checkpoint reduces the amount of replay needed;
old files are retained rather than automatically pruned.

Only calls through the proxy are intercepted. Direct access to mutable objects,
readonly methods that mutate, and unlocked calls can break the correspondence
between live and recovered state. Deterministic method behavior and recorded
clock values are required. Recovery also repeats external effects in domain
methods.

Successful calls normally flush the journal to the operating system without
syncing it to disk. Clean restart recovery does not imply power-loss durability
or complete recovery from a corrupted file. Some replay and decoding errors are
logged and recovery continues. Read :doc:`usage` before relying on persisted
state, and :doc:`snapshots` for the checkpoint publication boundary.

Start with the executable :doc:`tutorial`. All pickle storage must be trusted.
