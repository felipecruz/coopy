Typed domain objects and persistence controls
=============================================

Async callers and concurrent-reader guarantees are covered in:

.. toctree::
   :maxdepth: 1

   concurrency

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

Serialization and schema migration
----------------------------------

Pickle remains the default, including its existing stream memo and file names.
Old unsigned and HMAC-protected pickle storage remains readable. Explicit
``serializer=coopy.PickleSerializer()`` has the same wire format. Pass the same
serializer, type registry, schema configuration and secret whenever reopening.
Storage format is not auto-detected or converted in place.

JSON is opt-in and only constructs registered application types. For example::

    registry = coopy.TypeRegistry()

    def restore_todo(state):
        todo = Todo()
        todo.__dict__.update(state)
        return todo

    registry.register("todo.v1", Todo,
                      encode=lambda todo: vars(todo), decode=restore_todo)
    codec = coopy.JsonSerializer(registry)
    with coopy.control(coopy.open(Todo, "json-data", serializer=codec)) as todo:
        todo.add("milk")

Register every domain type in the graph under a stable name. Each encoder
returns supported state; each decoder validates that state and returns exactly
the registered class. Decoders are trusted application code. JSON supports
None, booleans, finite numbers, strings, bytes, dates, datetimes, lists, tuples,
dictionaries and registered objects; Action and the recorded clock have
built-in codecs. Date/time values retain their ISO representation, not named
time-zone identity. Cycles and shared container/object identities are rejected;
use pickle for such graphs. Value-like immutable scalars can be repeated.
JSON does not provide protection against resource exhaustion from huge inputs.

A custom serializer implements ``Serializer``: ``writer(file)`` returns an
object with ``dump(value)`` and ``clear_memo()`` (called on journal rotation);
``reader(file)`` returns an object with ``load()`` that consumes exactly one
record. ``dumps(value)`` and ``loads(bytes)`` handle one independent record for
signed storage. Files are binary. The application is responsible for its
codec's safety and stable encoding. JSON uses newline-terminated version-1
records, with no pickle fallback; unknown names and versions fail explicitly.

Journal actions now carry ``schema_version``. Old actions without it mean
version 1. Versions are per method, default to 1, and must advance in consecutive
steps. To upgrade old ``add(text)`` calls to a signature requiring priority::

    schemas = coopy.ActionSchemas({"add": 2})
    schemas.register("add", 1,
                     lambda args, kwargs: (args, dict(kwargs, priority=0)))
    todo = coopy.open(Todo, "data", schemas=schemas)

An upcaster receives copied positional arguments and keyword arguments and
returns ``(tuple_args, dict_kwargs)``. Coopy advances the version after each
successful step and checks the resulting call signature before replay.
Upcasters must be deterministic and free of external effects. Keep all needed
upcasters until older journals are no longer recovery inputs. New writes use
the configured current version. Do not mutate configuration while a system is
open. Method renaming and automatic snapshot-state migration are not provided;
use explicit registered codecs or a domain compatibility method for these.

For moved or renamed pickle classes, map the old module and class name to the
current class::

    codec = coopy.PickleSerializer(
        class_aliases={("old_package.todo", "OldTodo"): Todo})
    todo = coopy.open(Todo, "data", serializer=codec)
    coopy.control(todo).take_snapshot()
    coopy.control(todo).close()

Aliases apply to snapshots and journal arguments. The replacement class must
accept the old state (or implement compatible pickle state restoration).
Back up storage first; retain aliases while old files remain recovery inputs.
Aliases are not a pickle allowlist. They do not restrict other pickle globals.

Unknown types, unsupported versions, missing or invalid upcasters, and decode
errors stop strict recovery with ``RecoveryError``. Salvage returns the valid
prefix and the stop report without writing. Write-time serialization failures
raise ``PersistenceError`` for journals (with ``SerializationError`` as the
cause), because memory may already have changed. A snapshot encoding failure
leaves the previous checkpoint usable. Changing formats requires an explicit
export/import to a new directory; no conversion command is provided.

Trust boundaries
~~~~~~~~~~~~~~~~

Never load arbitrary pickle. F14 HMAC integrity authenticates bytes before any
codec runs, but **does not make arbitrary pickle safe**, encrypt data, or prove
freshness. A trusted signer can still produce an executable malicious pickle.
Keep secrets outside storage. JSON never imports a class named by input, but
registered decoders and replayed domain methods are trusted executable code.

Replication retains its trusted-peer pickle protocol regardless of the disk
serializer. JSON storage does not make replication safe for untrusted peers;
run peers with compatible domain code and schema configuration. Upcasters here
apply to disk recovery, not heterogeneous-version network replication.
