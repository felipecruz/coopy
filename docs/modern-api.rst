Typed domain objects and persistence controls
=============================================

Both ``coopy.init_persistent_system(Todo, directory)`` and
``coopy.init_persistent_system(Todo(), directory)`` retain the domain type for
static checking. Decorators preserve positional and keyword signatures. The
installed package includes ``py.typed``. Salvage returns
``RecoveryResult[Todo]``; its ``system`` can be ``None`` when no checkpoint can
be decoded. It is not a writable persistent system.

Use ``coopy.control(todo).take_snapshot()`` and ``coopy.control(todo).close()``
for persistence operations. Domain methods named ``close``, ``shutdown``, or
``take_snapshot`` take precedence and are journaled normally. Legacy direct
controls remain available at runtime when the domain has no matching name;
use the control handle for typed code. Other proxy implementation attributes
(such as ``obj``, ``lock`` and ``publisher``) remain reserved.

Typing is gradual: decorators, errors and integrity use strict checks; base
requires annotated definitions. Dynamic replay and networking internals are
not yet strictly checked.

Opening and closing
-------------------

``coopy.open`` is the same function as ``coopy.init_persistent_system``;
imports from ``coopy.base`` remain supported. Direct context management works::

    with coopy.open(Todo, "data/") as todo:
        todo.add("milk")

Exit closes journals and replication resources and stops the snapshot timer.
It does not take an implicit snapshot. Close is idempotent; subsequent domain
calls raise ``LifecycleError``. A body exception propagates unchanged even if
cleanup also fails (that cleanup failure is logged). All resources are attempted.

Python typing cannot express an intersection of an arbitrary domain class and
a context manager. For a typed context use::

    with coopy.control(coopy.open(Todo, "data/")) as todo:
        todo.add("milk")

Directories accept strings and ``os.PathLike[str]`` (including ``Path``).
Storage uses native pathlib paths and creates missing parent directories.
Legacy path helpers still return strings; backslashes in public input follow
the host platform's native path rules.

Replication names and errors
----------------------------

Use ``coopy.control(todo).start_primary(...)`` and ``start_replica(...)``.
``start_master`` and ``start_slave`` are deprecated aliases that emit
``DeprecationWarning``. They remain through v0.7 and v0.8, with removal planned
for v0.9. Existing role fields and the wire protocol are unchanged.

Library errors derive from ``coopy.CoopyError``: ``ConfigurationError``,
``PrevalentError``, ``PersistenceError``, ``LifecycleError``,
``ReplicationError``, ``IntegrityError``, and ``RecoveryError``. Existing
imports from journal, integrity and restore remain supported. Configuration
and integrity errors still derive from ValueError; persistence, lifecycle,
replication and recovery errors from RuntimeError. Domain exceptions and
underlying OS errors retain their original types where they propagate.

Logging
-------

Initialization does not configure logging or create a log file. Applications
own their handlers and levels. To opt into the old rotating file handler, call
``coopy.logging_config(directory)`` explicitly; the directory must exist.
Repeated calls for the same file do not duplicate its handler.
