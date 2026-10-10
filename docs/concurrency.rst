Async callers and free-threaded Python
======================================

``AsyncPersistent`` runs opening/recovery, domain calls, checkpoints and close
on one dedicated writer thread per instance. The event loop never takes the
domain's ``threading.RLock`` or performs storage I/O::

    import asyncio
    from coopy import AsyncPersistent
    from coopy.decorators import readonly

    class Todo:
        def __init__(self):
            self.items = []

        def add(self, text):
            self.items.append(text)
            return len(self.items)

        @readonly
        def list_items(self):
            return tuple(self.items)

    async def main():
        async with AsyncPersistent(Todo, "todo-data") as todo:
            await todo.add("milk")
            await asyncio.gather(todo.add("eggs"), todo.add("bread"))
            print(await todo.list_items())
            await todo.take_snapshot()

    # Put Todo in an importable module for recovery in another process.
    # asyncio.run(main())

For explicit lifecycle management use
``todo = await AsyncPersistent.open(Todo, path)`` and ``await todo.aclose()``
in ``finally``. Construction alone does not open storage or start a thread;
enter the context or use ``open`` before domain calls. An instance opens once,
belongs to one event loop, and cannot be shared across loops or called directly
from another thread. Use ``asyncio.run_coroutine_threadsafe`` to submit to its
owning loop if necessary. Keep one proxy/facade per storage directory.

Ordering and reads
------------------

Calls enter the FIFO writer queue when their coroutines execute, not when the
coroutine objects are constructed. Sequential awaits preserve order; concurrent
tasks are ordered by submission to the owning event loop. Each operation
finishes, including its durability acknowledgment, before the next begins.
Queries and snapshots use the same queue. Reopening uses normal journal replay
and the same deterministic-domain requirements as the synchronous API.

Domain methods remain ordinary synchronous methods, not ``async def``. Use
``@readonly`` methods returning immutable values or detached copies for queries.
Attributes are not asynchronously exposed: ``await todo.items()`` raises
``TypeError``. Method resolution also runs on the writer. The facade reserves
``open``, ``call``, ``aclose`` and ``take_snapshot``; use
``await todo.call("aclose", argument)`` for a colliding domain method.
Only public domain names are exposed. ``coopy.control`` is for synchronous
proxies; async persistence controls are ``aclose`` and ``take_snapshot``.

Domain dispatch is dynamically typed: methods return ``Any`` to type checkers;
this facade does not preserve arbitrary domain method signatures. Constructor
options are forwarded to ``coopy.open`` and validated on the writer, except
that salvage is rejected. Use synchronous salvage explicitly for inspection.

Cancellation, failures and shutdown
-----------------------------------

Cancelling an awaiting task does **not** cancel an accepted operation, even if
it is still queued. It may mutate and persist after cancellation. Do not retry
a cancelled write blindly. Its result or error is no longer delivered to that
cancelled waiter; use a query after the write, or retain and shield the caller's
task when its outcome is needed. Cancelling before submission performs no call.

Domain and persistence exceptions propagate to an active waiter unchanged;
domain exceptions do not stop later queued calls. Normal ``@abort_exception``
semantics still apply. Persistence failure can leave memory changed and causes
subsequent mutations/checkpoints to be refused by the underlying journal.
There is no rollback. Closing does not re-raise errors from previous writes.

``aclose`` rejects new calls once its coroutine executes, drains all accepted
work, closes storage, and joins the writer without blocking the event loop.
It takes no implicit snapshot. Repeated/concurrent closes await the same result,
including a cleanup error. Cancelling a close waiter leaves cleanup running;
await ``aclose`` again before stopping the event loop. Cancellation during
opening waits for initialization and cleanup; another cancellation can interrupt
that wait, in which case explicitly await ``aclose`` again. Failed initialization
propagates its original error and shuts down the executor. Context exit preserves
a body exception if cleanup also fails, logging the cleanup error.

The queue is unbounded. Limit application concurrency for backpressure. There
is no forced termination or close timeout: a hung domain method or storage call
can delay shutdown indefinitely. Threads cannot safely interrupt mutations.
CPU-heavy code can still contend for the GIL on standard Python, and a native
extension holding the GIL can stall the loop. This is not CPU isolation.

Performance controls
--------------------

``durability="sync"`` waits for fsync on the writer before returning. The
``group_commit_delay`` option remains accepted, but a single sequential writer
cannot batch multiple facade calls; a positive delay adds latency without
batching benefit. Leave it at zero. Async snapshots use the blocking algorithm
on the writer; fork snapshots are unsuitable for this multithreaded lifecycle.
Snapshot timers and replication controls are not exposed by the facade.

Readers without the GIL
-----------------------

The synchronous proxy uses an explicit reentrant lock for ordinary methods,
including ``@readonly`` queries. A query through the proxy sees a coherent
state relative to other locked methods and blocking snapshots. This guarantee
does not depend on the GIL. Multiple query calls are not one atomic transaction;
put a compound query in a single domain method. Under synchronous group commit,
a query can see an applied write before the writer's fsync acknowledgment.

Neither the GIL nor built-in container locks protect a multi-field application
invariant. Direct attributes, properties, ``proxy.obj``, retained input objects,
and mutable references returned by a method have **no coordinated read or
snapshot guarantee**. Do not read or mutate those while other threads operate;
even copying a live collection outside the proxy lock can race. Return copies
inside a locked query, copy nested mutable contents as needed, and avoid sharing
mutable call arguments with other tasks while queued/executing or retaining
aliases into domain state. Direct mutation is never automatically journaled.
Static serializer/schema configuration must not be mutated while open.

``@unlocked`` skips the proxy lock, including for readonly methods. Such calls
can race with writers, shared clock recording and snapshots. They require
application-provided synchronization and are outside these guarantees. Grouped
synchronous writes happen to acquire the lock even if marked unlocked; do not
rely on that as a general contract. The async queue serializes its own calls,
but cannot protect against direct access or external domain threads. Readonly
is a declaration, not an enforcement of immutability. Lifecycle/control changes
on a synchronous proxy should be coordinated by the owner after stopping callers.

CI is configured to run the core suite on Python 3.14t on Linux/macOS,
with ``PYTHON_GIL=0`` and assertions checking that the interpreter actually has
the GIL disabled. Concurrency tests overlap multiple readers, writers and
snapshots, check multi-field consistency, and compare reopened state with the
live result. The free-threaded jobs omit optional compression extensions;
compression remains covered by the regular interpreter matrix. These tests do
not certify arbitrary domain code or third-party extensions as thread-safe.

See Python's `free-threading guidance
<https://docs.python.org/3/howto/free-threading-python.html>`_ and the
`setup-python free-threaded configuration
<https://github.com/actions/setup-python/blob/main/docs/advanced-usage.md#free-threaded-python>`_.
