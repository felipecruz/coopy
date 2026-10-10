Migrating stored data
=====================

Snapshots and journals keep the shape your code had when they were written.
When a domain class changes, pick the tool that matches what changed:

==================================  ==========================================
What changed                        Use
==================================  ==========================================
A journaled method's arguments      An action upcaster in ``coopy.ActionSchemas``
(added, removed, reordered)         (see :doc:`modern-api`). It rewrites old
                                    journal records before replay.
A class moved to another module     A class alias,
or was renamed                      ``coopy.PickleSerializer(class_aliases=...)``.
                                    It changes which class pickle constructs,
                                    not the state it receives.
The root domain object's fields     A ``__coopy_version__`` and registered
(added, renamed, restructured)      upgraders in ``coopy.StateSchemas``,
                                    described below. They upgrade the restored
                                    root object before journal replay.
Fields of objects nested inside     A class-level state version plus
the root                            ``__setstate__``, described below. It
                                    upgrades old state as pickle restores it.
==================================  ==========================================

These combine: a moved class whose fields also changed needs an alias and a
``__setstate__``; a method whose arguments follow a field split needs an
upcaster and a ``__setstate__``. Upcasters only see journal records, aliases
only change class lookup, state upgraders only see the restored root object,
and ``__setstate__`` only sees snapshot state (and pickled journal arguments
containing that class).

Registered state upgraders
--------------------------

Declare the root class's current state version in ``__coopy_version__`` and
register one upgrader per older version, mirroring ``coopy.ActionSchemas``::

    class TodoList:
        __coopy_version__ = 3  # items -> {"text", "done"} dicts -> tasks

        def __init__(self):
            self.title = "Todo"
            self.tasks = []

    def strings_to_dicts(todo):  # version 1 -> 2
        todo.items = [{"text": text, "done": False} for text in todo.items]
        return todo

    def rename_items(todo):  # version 2 -> 3
        todo.tasks = todo.__dict__.pop("items")
        todo.title = "Todo"
        return todo

    state_schemas = coopy.StateSchemas()
    state_schemas.register(TodoList, from_version=1, upgrade=strings_to_dicts)
    state_schemas.register(TodoList, from_version=2, upgrade=rename_items)
    todo = coopy.open(TodoList, "data", state_schemas=state_schemas)

How it works:

* Each snapshot of a class that declares ``__coopy_version__`` records that
  version alongside the state. Snapshots of classes that declare none keep the
  0.6.0 layout. A snapshot without a recorded version, including every snapshot
  written by 0.6.0, is version 1.
* Recovery loads the latest snapshot, then calls the upgraders for each
  version from the stored one up to the current one, in order, and only then
  replays the journal. An upgrader receives the restored root object in the
  old shape (pickle restores the stored attributes without calling
  ``__init__``) and returns an instance of the same class in the next shape.
* A missing upgrader, a stored version newer than the class's (or invalid), an
  upgrader that raises, or one that returns another type is a checkpoint
  failure: strict recovery raises ``RecoveryError``; salvage returns no system
  and reports the failure in ``report.stop``.
* Journal records are not upgraded by state upgraders. Methods replayed after
  the snapshot run on the upgraded object, so keep their signatures compatible
  or add action upcasters.
* With ``coopy.JsonSerializer`` the registered decoder still receives the old
  stored dictionary and must construct the object; the upgraders then reshape
  it.

Upgraders and ``__setstate__`` combine: nested objects upgrade themselves while
pickle restores them, then the root's upgraders run.

Upgrading nested state with ``__setstate__``
--------------------------------------------

State upgraders handle the root object. Objects stored inside it, and
applications that prefer to keep migrations in the class, can version their
state themselves. Pickle calls ``__setstate__`` with the stored dictionary
instead of restoring ``__dict__`` directly, so a class can inspect old state and
upgrade it in steps:

* Give the class a ``STATE_VERSION`` and write it into the state from
  ``__getstate__``. State written before you add the marker counts as version 1.
* In ``__setstate__``, apply each upgrade whose version is newer than the stored
  one, in order, then update ``__dict__``. Reject versions newer than the code.
* Keep every step while older snapshots, or journals recorded before the next
  snapshot, can still be recovery inputs.

The maintained example evolves an address book's ``Contact`` through three
changes: adding ``email`` with a default, renaming ``phone`` to ``telephone``,
and splitting ``name`` into ``first_name`` and ``last_name``. The ``add``
method's arguments changed with the split, so it also has an upcaster:

.. literalinclude:: examples/address_book.py
   :language: python

The script below restores a data directory written by the first release
(``docs/examples/fixtures/address_book_v1``, regenerated by
``scripts/make_state_migration_fixture.py``). Its snapshot holds version 1
contacts and its journal holds a later version 1 ``add(name, phone)`` call:

.. literalinclude:: examples/state_migration.py
   :language: python

The documentation tests run this script against the committed fixture.

Notes and limits:

* Upgrades run every time old state is loaded. Take a snapshot after upgrading
  so later restores read the current shape; old files are kept, not rewritten.
* ``__setstate__`` and upcasters run during recovery and must be deterministic
  and free of external effects, like replayed methods.
* An exception raised by ``__setstate__`` is a decode failure: strict recovery
  stops with ``RecoveryError`` and salvage reports it.
* Classes with ``__slots__`` and no ``__dict__`` receive a ``(None, slots)``
  pair; upgrade the slot dictionary the same way.
* The root domain object can use the same pattern.
* With ``coopy.JsonSerializer``, ``__setstate__`` is not involved: put the
  version in the encoder's output and upgrade in the registered decoder.

Back up a data directory before opening it with new code: the first snapshot
afterwards is written in the new shape, which older code cannot read.
