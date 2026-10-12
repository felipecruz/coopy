coopy
=====

**Persistence for plain Python objects.** No database, no ORM, no schema: wrap
an object once, keep calling its methods, and it survives restarts.

What is it?
-----------

Most applications keep their data in a database and copy it into objects when
they need it. coopy turns this around: **your objects live in memory, and the
disk is just a log of what happened to them.** The technique is called
`object prevalence`_.

coopy wraps your object in a proxy. Every time you call a method that changes
state, the call itself (method name and arguments) is appended to a journal on
disk before the result is returned. Every so often, coopy saves a snapshot of the
whole object so the journal stays short. When your program starts again, coopy
loads the latest snapshot and replays the calls made after it: same calls, same
order, same state.

.. code-block:: text

    your code ──► proxy ──► your object (in memory)
                    │
                    └──► journal:  deposit("alice", 100)
                                   transfer("alice", "bob", 30)
                                   ...

    restart:   latest snapshot ──► replay the journal ──► the same object

A complete example
------------------

A bank whose accounts survive a restart. ``Bank`` is an ordinary class; the
only coopy-specific line is ``coopy.open``:

.. literalinclude:: examples/quickstart.py
   :language: python
   :lines: 3-

Run it with ``python docs/examples/quickstart.py``. Install coopy with
``python -m pip install coopy`` (Python 3.10 or newer); see :doc:`installation`.

Why coopy
---------

* **Your code stays yours.** Domain classes are plain Python: no base class,
  no mapping layer, no queries. Type checkers see the proxy as your class.
* **Memory speed.** Reads are attribute access. A query is a Python
  expression over your own objects.
* **History for free.** The journal records every change as a named command
  with its arguments and recorded time. :doc:`Rebuild any earlier moment <usage>`
  or inspect it with the :doc:`command-line tool <cli>`.
* **Safe by default.** Calls are serialized under a lock, a data directory has
  one writer, recovery stops on corruption instead of guessing, and
  ``durability="sync"`` acknowledges a call only after it is on disk.
* **Grows with you.** Snapshots, pruning, migrations, signed storage, JSON
  storage, async callers, ``@transactional`` rollback and experimental
  :doc:`replication`.

The one rule: replay must give the same result
----------------------------------------------

Recovery runs your methods again, so they must be deterministic:

* Change state only by calling methods on the proxy.
* Use ``self._clock.now()`` instead of ``datetime.now()``, and ``self._env``
  for random numbers, UUIDs and tokens. coopy records the values and returns
  the same ones on replay (see :doc:`use_clock` and :doc:`use_env`).
* Do network calls, file reads and other side effects outside, and pass the
  results in as arguments.

coopy checks your methods for the usual mistakes when it opens a system.

When not to use it
------------------

Your data must fit in memory, one process writes to a data directory, and
snapshots and journals use ``pickle`` by default, so only load data you
trust. If you need ad-hoc SQL from other teams or data larger than RAM, use a
database.

Where next
----------

* :doc:`tutorial`: open, checkpoint, close and reopen a system step by step,
  then try the interactive todo-list demo.
* :doc:`usage`: the durability and recovery contract.
* :doc:`snapshots`, :doc:`migrations` and :doc:`cli` for running coopy in
  production.
* :doc:`modern-api` and :doc:`api` for typed APIs and the full reference.

coopy is released under the `BSD License`_. Source and issues:
https://github.com/felipecruz/coopy

.. toctree::
   :caption: Getting started
   :maxdepth: 2
   :hidden:

   installation
   tutorial

.. toctree::
   :caption: User guide
   :maxdepth: 2
   :hidden:

   usage
   basics
   use_clock
   use_env
   method_decorators
   snapshots
   migrations
   modern-api
   concurrency
   cli
   client_server
   replication

.. toctree::
   :caption: Reference
   :maxdepth: 2
   :hidden:

   api
   util_api
   performance

.. toctree::
   :caption: Project
   :maxdepth: 1
   :hidden:

   development
   tests
   changelog
   roadmap

.. _BSD License: http://www.opensource.org/licenses/bsd-license.php
.. _object prevalence: https://en.wikipedia.org/wiki/System_prevalence
