.. _method_decorators:

Method Decorators
-----------------

@readonly
=========

This decorator means thar your method will not mofidy business objects. Like a get method from a Wiki class. Therefore, this method will not generate a log entry at coopy actions log::

    from coopy.decorators import readonly
    @readonly
    def get_page(self, id):
        if id in self.pages:
            return self.pages[id]
        else:
            return None

@unlocked
=========

How coopy assures thread-safety? By synchronizing method invocations using a reetrant lock.

This decorator provides a means of leaving the thread safety in your hands via the @unlocked decorator. Using this decorator, you should implement concurrency mechanism by yourself.

@abort_exception
================

By default, a non-readonly method call is journaled even when it raises an
exception. Restore re-executes that call, including any mutations made before
the failure.

``@abort_exception`` omits a call from the journal only when it raises. The
exception still reaches the caller. Successful calls return their result and
are journaled normally, so their mutations survive a clean restart. For
example, validate before changing state::

    from coopy.decorators import abort_exception

    @abort_exception
    def create_page(self, page):
        if page.id in self.pages:
            raise ValueError('Page already exists')
        page.last_modified = self._clock.now()
        self.pages[page.id] = page
        return page

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
