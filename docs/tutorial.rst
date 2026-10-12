Persistence and recovery tutorial
=====================================

A persistent system wraps a domain object in a proxy. Call methods on that
proxy to record mutations. Keep the domain class in an importable Python module
so pickle can find the same class when another process reopens the directory.
The maintained example uses ``docs/examples/wiki.py``:

.. literalinclude:: examples/wiki.py
   :language: python

``@readonly`` excludes queries from journaling; it does not enforce immutability.
This query returns a copy whose values are immutable. ``@abort_exception``
records successful calls and omits failed ones, so validation happens before
mutation. The injected ``self._clock`` records each time value for replay.
There is no ``from coopy import clock`` import.

Open, checkpoint, close, and reopen
---------------------------------------

Save the following as ``persistence.py`` alongside ``wiki.py``. It uses a
temporary data directory, checks snapshot state plus later journal entries,
verifies recorded clock values, and writes again after reopening:

.. literalinclude:: examples/persistence.py
   :language: python

From an installed source checkout, run ``python docs/examples/persistence.py``.
Both ``Wiki`` (a no-argument class) and ``Wiki()`` (an instance) are accepted by
``coopy.base.init_persistent_system``. Use a stable, dedicated directory in a
real application; the temporary directory here is deleted when the example
finishes. Reopening from another process requires the same importable domain
module and compatible code and dependencies. Always stop application writers
and call ``close()`` before reopening. Closing does not take a snapshot unless
you ask for one (see :ref:`snapshot-on-close`).

For the storage contract and recovery precautions, read :doc:`usage` and
:doc:`snapshots`. See :doc:`method_decorators` for failure behavior and
:doc:`use_clock` for deterministic time handling.

Interactive demo
----------------

``docs/examples/todo_demo.py`` is a small todo-list shell built on coopy. Run it
from a source checkout and pass a directory to keep the data between runs::

    python docs/examples/todo_demo.py ./my-todos

Besides ``add``, ``done``, ``edit``, ``delete``, ``search`` and ``list``, it has
persistence commands that show what coopy does underneath: ``snapshot`` takes a
checkpoint, ``inspect`` shows the data directory, ``journal`` lists the
recorded method calls, and ``reopen`` closes the system and recovers it from
disk. Type ``help`` for the full list. Without a directory argument, the demo
uses a temporary directory that is removed on exit.
