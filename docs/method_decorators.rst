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

Executable failure example
==========================

This intentionally mutates before raising to show the difference between live
and recovered state. Run ``python docs/examples/decorator_semantics.py`` from
the checkout. An ordinary failed call is replayed; the failed abort-decorated
call is omitted. A snapshot before closing would capture both mutations.

.. literalinclude:: examples/decorator_semantics.py
   :language: python
