.. _use_clock:

Recorded clock values
=====================

Each method invocation through the proxy gets a fresh ``self._clock``. Use it
inside domain methods; it is not a package-level import or a clock to use in
``__init__``. The journal stores the ordered results of clock calls, not just
the action's timestamp. Recovery returns those results in order, so multiple
calls in one action retain their individual values. The clock of a call is
held in a context variable, so concurrent ``@unlocked`` calls each record their
own values (:doc:`method_decorators`); outside a proxy call ``self._clock``
reads the system clock without recording.

The tutorial's domain uses the three date methods:

.. literalinclude:: examples/wiki.py
   :language: python
   :pyobject: Wiki.create_page

.. list-table:: Clock API
   :header-rows: 1

   * - Method
     - Result
   * - ``self._clock.now(tz=None)``
     - Like ``datetime.now(tz)``: aware ``datetime`` in ``tz``, or naive local
       time without ``tz``.
   * - ``self._clock.utcnow()``
     - Naive UTC ``datetime`` (no timezone attached), like the deprecated
       ``datetime.utcnow()``.
   * - ``self._clock.today()``
     - Local ``date``.
   * - ``self._clock.time()``
     - Seconds since the epoch as a ``float``, like ``time.time()``.
   * - ``self._clock.monotonic()``
     - ``time.monotonic()``: subtract two calls in the same method to measure a
       duration. Recorded values come from the original process, so never
       compare them across calls or restarts.

Prefer aware UTC
----------------

Naive ``now()`` values depend on the host's timezone, and ``utcnow()`` values
carry no timezone, so comparing them with aware values raises ``TypeError``.
For new code record aware UTC and convert to local time only for display::

    from datetime import timezone

    class Orders:
        def place(self, item):
            self.orders.append((item, self._clock.now(timezone.utc)))

Aware values keep their offset through pickle and JSON storage, snapshots and
replication. Pickle also keeps a ``zoneinfo.ZoneInfo`` timezone; JSON stores
the ISO 8601 offset, so a ``ZoneInfo`` comes back as a fixed-offset
``datetime.timezone`` that compares equal but no longer follows daylight
saving rules. Switching existing code from ``now()`` to ``now(timezone.utc)``
does not change replay of journals already written: old actions replay the
naive values they recorded.

Replay
------

The executable :doc:`tutorial` verifies that all three values from a call after
the checkpoint survive journal replay unchanged. Replay must make the same
clock calls in the same order. When it does not, replay raises
``coopy.ClockDivergenceError`` with the action name, the zero-based clock call
``index`` and the ``expected`` and ``actual`` call: ``today()`` where a
``datetime`` was recorded, ``now()``/``utcnow()`` where a ``date`` or ``float``
was recorded, ``now(tz)`` where a naive ``datetime`` was recorded,
``time()``/``monotonic()`` where no ``float`` was recorded, a call after the
recorded values ran out, or recorded values left unused when the method
returns. Recovery reports it as a ``clock`` stop (even
if the domain method caught the exception) and replicas become unsynchronized.
Since on-disk format 2, the journal stores each value with the name of the
call that produced it, as a ``(method, value)`` pair, so replay also rejects a
different call with a value of the same type (``utcnow()`` where ``now()`` was
recorded, ``monotonic()`` where ``time()`` was recorded) and ``now(tz)`` whose
timezone gives a different offset than the recorded value; ``expected`` names
the recorded call, for example ``now() returning datetime(...)``, and
``actual`` the replayed one. Actions written by earlier releases store bare
values and keep the older checks: same-typed calls swapped, or ``now(tz)``
with a different timezone, are not detected there. Replay returns the
recorded value unconverted. Random numbers, UUIDs and tokens are recorded
by ``self._env`` (:doc:`use_env`); external I/O is not captured, see
:doc:`usage`.

Type hints
----------

Annotate the injected clock with the ``coopy.Clock`` protocol::

    from datetime import datetime

    import coopy


    class Journal:
        _clock: coopy.Clock  # injected by coopy

        def __init__(self) -> None:
            self.entries: list[datetime] = []

        def record(self) -> datetime:
            stamp = self._clock.now()
            self.entries.append(stamp)
            return stamp

Live calls receive a recording ``RecordClock``; recovery and replicas inject a
replaying ``RestoreClock``. Both implement ``coopy.Clock``, so type checkers
see ``now(tz)`` and ``utcnow()`` returning ``datetime``, ``today()`` returning
``date``, ``time()`` and ``monotonic()`` returning ``float``, and reject any
other clock method. ``_clock: RecordClock``
annotations still type-check, but only describe the live clock.

Clock-aware validation
----------------------

Opening a system checks the source of each domain method for direct calls
that replay cannot reproduce. Names are resolved through the method module's
imports, so ``dt.now()`` after ``from datetime import datetime as dt``,
``datetime.datetime.now()`` and ``epoch()`` after ``from time import time as
epoch`` are all recognised. The check covers ``datetime``/``date``
``now()``, ``utcnow()`` and ``today()``; ``time.time()``, ``monotonic()`` and
``perf_counter()``; ``random.*``; ``uuid.uuid1()``/``uuid4()``;
``os.urandom()``; and ``secrets.*``. Each finding names the file, line and the
``self._clock`` or ``self._env`` call to use instead (see :doc:`use_env`).
Every ``self._clock`` and ``self._env`` call, including ``now(timezone.utc)``,
``time()`` and ``monotonic()``, is accepted.

Choose what happens with ``validation=`` when opening:

* ``"warn"`` (default): logs a warning for each call, but still raises
  ``coopy.error.NonDeterministicCallError`` for ``datetime.now()``,
  ``datetime.utcnow()`` and ``date.today()`` written that way, as earlier
  releases did.
* ``"strict"``: raises ``NonDeterministicCallError`` (a ``PrevalentError``)
  for every call found. Its ``calls`` attribute lists each
  ``coopy.validation.NonDeterministicCall``.
* ``"off"``: skips the check.

Methods without available source, such as classes defined in a REPL, are
skipped with a warning. Calls made through helpers in other functions, values
stored on the domain (``self.rng.random()``), ``getattr`` or other dynamic
lookups escape detection, so passing validation does not prove deterministic
behavior. For tests, install a ``coopy.testing`` clock; see :doc:`util_api`.
