.. _method_decorators:

Method Decorators
-----------------

@readonly
=========

``from coopy.decorators import readonly`` marks a query as excluded from the
journal and replication, whether it returns or raises. It still takes the
proxy lock unless also decorated with ``@unlocked``. It does not enforce
immutability: return detached copies or immutable values, as in the tutorial.

.. literalinclude:: examples/wiki.py
   :language: python
   :pyobject: Wiki.get_page

@unlocked
=========

``from coopy.decorators import unlocked`` skips the proxy's reentrant lock.
It does not suppress journaling. The application must coordinate concurrent
calls and snapshots itself. Unlocked mutations are outside the checkpoint
consistency guarantee; avoid them in persistent domains unless you provide
equivalent synchronization.

Unlocked methods may use ``self._clock`` and ``self._env``. Every proxy call
records into its own clock, kept in a context variable rather than on the
domain object, so overlapping unlocked calls never record into each other's
action and each one replays exactly the values it read. Values are recorded
only in the thread (or task) that made the proxy call: a thread the method
starts itself reads live, unrecorded values unless it runs in a copy of the
caller's context (``contextvars.copy_context().run``). Recording does not order
the calls themselves: replay runs journaled actions one at a time in journal
order, so overlapping unlocked writers must change independent state (or
synchronize) for replay to rebuild the same state, and two unlocked writers
must not publish at the same moment, because journal writes are not
serialized for them.

These limits also apply on free-threaded Python: the GIL is not a substitute
for locking compound reads. See :doc:`concurrency` for reader guarantees,
direct-object access limits, and the asyncio facade.

@abort_exception
================

By default, a non-readonly method call is journaled even when it raises an
exception. Restore re-executes that call, including any mutations made before
the failure.

``@abort_exception`` omits a call from the journal only when it raises. The
exception still reaches the caller. Successful calls return their result and
are journaled normally, so their mutations survive a clean restart. The
tutorial validates before changing state:

.. literalinclude:: examples/wiki.py
   :language: python
   :pyobject: Wiki.create_page

Combining ``@readonly`` and ``@abort_exception`` in either order excludes both
successful and failing calls from the journal. ``@readonly`` is a declaration
by the application; it does not prevent mutations.

**This decorator does not roll back in-memory mutations or external effects.**
Changes made before an exception remain visible in the running object and can
be captured by a later snapshot. Without that snapshot, replay omits the failed
call, so recovered state can differ from the live state after failure. Perform
validation before mutations and arrange any required compensation yourself.
Pre-call subscriber notifications still occur for non-readonly calls, including
ones that later fail. Successful calls are also published to replication
subscribers; failed abort-decorated calls are not.

@transactional
==============

``from coopy.decorators import transactional`` makes a failed call leave the
domain exactly as it was before the call, both in the running process and
after a restart. Before each call the proxy deep-copies the domain object's
attributes (``vars(obj)``, except the injected ``_clock`` and ``_env``). If the
method raises (any exception, including ``KeyboardInterrupt``), the copy
replaces the attributes in place and the exception reaches the caller. Like
``@abort_exception``, the failed call is not journaled, not replicated and not
sent to ``receive_exception``; successful calls are journaled normally.

.. code-block:: python

    from coopy.decorators import transactional

    class Accounts:
        @transactional
        def transfer(self, source, target, amount):
            self.balances[source] -= amount
            if self.balances[source] < 0:
                raise ValueError("insufficient funds")  # the debit is undone
            self.balances[target] += amount

Rules:

* The domain object keeps its identity, and references back to it (a child
  holding ``self``) keep pointing at it. After a rollback, the other attribute
  values are the copies: references a caller obtained before the call (for
  example ``items = system.items``) point at discarded objects. A successful
  call keeps every object as it was.
* State that cannot be deep-copied (locks, open files, sockets) makes the call
  fail with ``ConfigurationError`` before the method runs; nothing is changed
  or published.
* ``@transactional`` cannot be combined with ``@readonly`` (queries do not
  need it) or ``@unlocked`` (a copy taken while other calls run would be torn,
  and restoring it would undo their changes); accessing such a method raises
  ``ConfigurationError``.
* Nested calls: a method calling another method on ``self`` is plain Python,
  so the whole outermost call is one unit and decorators on the inner method
  have no effect. An exception the outer method catches is not a failure, so
  nothing is undone for it. A call made through the proxy from inside another
  call (the lock is reentrant) takes its own copy and rolls back to its own
  start, like a savepoint; the outer call can catch the exception and continue.
* External effects (files written, messages sent) are never undone.
* Journal failures: with ``durability="sync"``, if writing or syncing the
  record fails before the record is complete on disk, coopy truncates the
  journal back to where the record started (and syncs that), restores the copy
  and raises ``PersistenceError`` with ``record_discarded = True``. If the
  record is already complete (for example a later rotation fails), it will be
  replayed, so memory is not rolled back and ``record_discarded`` is
  ``False``. In both cases the journal is failed and refuses later writes.
  Non-transactional calls keep the record and their changes, as before. With
  group commit, a failure of the shared batch sync is not rolled back.
* Recovery and replicas never roll back: they only re-execute successful
  calls, and a replayed call that raises is a divergence as before. Replicas
  refuse transactional calls like any other write.

**Cost.** Every call copies the whole domain state, so its latency and its
temporary memory grow with the state size, not with what the call changes.
Peak memory during a call is up to twice the state. Measured on Python 3.12
(Apple silicon, buffered journal) with a dict of ``[int, str]`` entries: an
ordinary call took 20–40 µs; a transactional one about 0.12 ms with an empty
dict, 1.2 ms with 1,000 entries, 11 ms with 10,000 and 120 ms with 100,000,
about 1 µs per copied entry. Use it for small domains or rare calls; for large
ones, validate before mutating (see ``@abort_exception``) or keep the state a
transactional method may touch small.

**Why snapshot and restore.** Copy-on-write would only copy what a call
changes, but Python cannot intercept mutations of arbitrary objects without
replacing every container with a tracking proxy (changing the domain's types
and slowing every access), and process-level copy-on-write (``fork``) cannot
hand a restored state back to the running process. Snapshot and restore works
with unmodified domain classes, so it is the chosen opt-in mechanism, at the
cost above. A per-system policy that makes every write transactional is not
provided, because that cost would apply to every call.

Executable failure example
==========================

This intentionally mutates before raising to show the difference between live
and recovered state. Run ``python docs/examples/decorator_semantics.py`` from
the checkout. An ordinary failed call is replayed; the failed abort-decorated
call is omitted. A snapshot before closing would capture both mutations. The
failed transactional call leaves nothing behind, live or after the restart.

.. literalinclude:: examples/decorator_semantics.py
   :language: python
