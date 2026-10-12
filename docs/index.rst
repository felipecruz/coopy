coopy
=====

**coopy** persists plain Python objects using snapshots and method-call
journals. It is released under the `BSD License`_.

Wrap your domain object with ``coopy.open`` (also available as
``coopy.base.init_persistent_system``) and call
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

Use :doc:`concurrency` for asyncio callers and thread-safety guarantees,
:doc:`migrations` for evolving stored state, and :doc:`cli` for inspecting,
verifying and converting closed data directories. The :doc:`api` lists current
signatures and available controls.

Restrictions
------------

Mutate state through proxy methods and keep their behavior deterministic.
Use the :doc:`recorded clock <use_clock>` for time and the
:doc:`recorded environment <use_env>` for random numbers, UUIDs and tokens,
pass other external inputs as arguments, and keep external effects outside replayed methods. Direct
changes to exposed mutable objects are not journaled.

Use one process and one persistent proxy per data directory; a second writable
open raises ``LockError``. Only load trusted
snapshots and journals: the default pickle serializer can execute code while
loading them. Opt-in JSON storage requires registered domain types
(see :doc:`modern-api`); replication always uses pickle. The
:doc:`persistence guide <usage>` describes strict recovery, salvage inspection,
and buffered versus synchronous durability.

Status
------

coopy requires Python 3.10 or newer. :doc:`replication` is experimental; it
does not provide durable replica journaling or automatic failover.

Contribute
----------

Source and issue tracking: https://github.com/felipecruz/coopy

See :doc:`installation`, :doc:`tests` and :doc:`development` to set up a checkout
and validate changes.

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
