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
calls, shared clock recording, and snapshots itself. Unlocked mutations are
outside the checkpoint consistency guarantee; avoid them in persistent domains
unless you provide equivalent synchronization.

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
