Persistence model
=================

Coopy keeps the domain object graph in memory. A proxy intercepts method calls
and records non-readonly actions in numbered journals (pickle by default,
with opt-in registered JSON; see :doc:`modern-api`). Recovery loads
the latest numbered snapshot, then re-executes actions from journals numbered
strictly after that snapshot. A checkpoint reduces the amount of replay needed;
old files are retained rather than automatically pruned.

Only calls through the proxy are intercepted. Direct access to mutable objects,
readonly methods that mutate, and unlocked calls can break the correspondence
between live and recovered state. Methods must behave deterministically.
Use the recorded clock and environment for time and randomness generated
inside methods, or pass those values as arguments. Recovery also repeats
external effects in domain methods.

Successful calls normally flush the journal to the operating system without
syncing it to disk. Clean restart recovery does not imply power-loss durability
or complete recovery from a corrupted file. Opt into ``durability="sync"`` for
per-action synchronization. Strict recovery stops at detected replay and
decoding errors; explicit salvage returns inspected state and a recovery
report. Read :doc:`usage` before relying on persisted state, and :doc:`snapshots`
for the checkpoint publication boundary.

Start with the executable :doc:`tutorial`. All pickle storage must be trusted.
