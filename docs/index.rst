.. coopy documentation master file, created by
   sphinx-quickstart on Tue May 18 18:06:23 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

coopy
-------

**coopy** persists plain Python objects using snapshots and method-call
journals. It is released under the `BSD License`_.

Wrap your domain object with ``coopy.base.init_persistent_system`` and call
methods on the returned proxy. No domain base class or ORM mapping is required.
The object graph stays in memory, so it must fit in memory. Reopening loads
the latest snapshot and replays subsequent journaled calls.

Request snapshots manually or schedule them through the proxy. Snapshots
reduce recovery work; old snapshots and journals are retained until you prune
them with ``coopy.control(system).prune(keep=N)`` or ``python -m coopy prune``
(see :doc:`cli`).

Using
-----

Follow the executable :doc:`tutorial` to open a persistent domain, record
mutations and clock values, take a checkpoint, close, and reopen it. Read
:doc:`usage` for the current durability and recovery contract and :doc:`basics`
for the storage model. Domain classes can be fully type-annotated; see
:doc:`modern-api` for how the proxy keeps their types.


Restrictions
------------

Mutate state through proxy methods and keep their behavior deterministic.
Use the :doc:`recorded clock <use_clock>` for time and the
:doc:`recorded environment <use_env>` for random numbers, UUIDs and tokens,
pass other external inputs as arguments, and keep external effects outside replayed methods. Direct
changes to exposed mutable objects are not journaled.

Use one process and one persistent proxy per data directory; a second writable
open raises ``LockError``. Only load trusted
snapshots and journals: they contain pickles that can execute code. The
:doc:`persistence guide <usage>` describes strict recovery, salvage inspection,
and buffered versus synchronous durability.

Status
------

coopy requires Python 3.10 or newer. :doc:`replication` is experimental; it
does not provide durable replica journaling or automatic failover.

Contribute
----------

Source and issue tracking: https://github.com/felipecruz/coopy

See :doc:`installation` and :doc:`tests` to set up a checkout and validate changes.

Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   tutorial
   usage
   cli
   basics
   use_clock
   use_env
   method_decorators
   snapshots
   migrations
   util_api
   client_server
   replication
   tests
   roadmap
   changelog
   todo

.. _BSD License: http://www.opensource.org/licenses/bsd-license.php
