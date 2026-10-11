.. _use_clock:

Recorded clock values
=====================

Each method invocation through the proxy gets a fresh ``self._clock``. Use it
inside domain methods; it is not a package-level import or a clock to use in
``__init__``. The journal stores the ordered results of clock calls, not just
the action's timestamp. Recovery returns those results in order, so multiple
calls in one action retain their individual values.

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
Journals store bare values, so ``now()`` and ``utcnow()`` replayed in each
other's place, ``time()`` and ``monotonic()`` swapped, or ``now(tz)`` with a
different timezone are not detected; replay returns the recorded value
unconverted. Randomness and external I/O are not captured
by this clock; see :doc:`usage`.

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

Initialization checks available method source for obvious direct uses such as
``datetime.now()`` and ``date.today()``; every ``self._clock`` call, including
``now(timezone.utc)``, ``time()`` and ``monotonic()``, is accepted. Some
patterns only warn, and aliases, helpers, or missing source can escape
detection. Passing validation does not
prove deterministic behavior. For tests, install a ``coopy.testing`` clock;
see :doc:`util_api`.
