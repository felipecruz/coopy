.. _use_clock:

Recorded clock values
=====================

Each method invocation through the proxy gets a fresh ``self._clock``. Use it
inside domain methods; it is not a package-level import or a clock to use in
``__init__``. The journal stores the ordered results of clock calls, not just
the action's timestamp. Recovery returns those results in order, so multiple
calls in one action retain their individual values.

The tutorial's domain uses all three supported methods:

.. literalinclude:: examples/wiki.py
   :language: python
   :pyobject: Wiki.create_page

.. list-table:: Clock API (no arguments)
   :header-rows: 1

   * - Method
     - Result
   * - ``self._clock.now()``
     - Naive local ``datetime``.
   * - ``self._clock.utcnow()``
     - Naive UTC ``datetime`` (no timezone attached).
   * - ``self._clock.today()``
     - Local ``date``.

The executable :doc:`tutorial` verifies that all three values from a call after
the checkpoint survive journal replay unchanged. Replay must make the same
clock calls in the same order. When it does not, replay raises
``coopy.ClockDivergenceError`` with the action name, the zero-based clock call
``index`` and the ``expected`` and ``actual`` call: ``today()`` where a
``datetime`` was recorded, ``now()``/``utcnow()`` where a ``date`` was
recorded, a call after the recorded values ran out, or recorded values left
unused when the method returns. Recovery reports it as a ``clock`` stop (even
if the domain method caught the exception) and replicas become unsynchronized.
Journals store bare values, so ``now()`` and ``utcnow()`` replayed in each
other's place are not detected. Randomness and external I/O are not captured
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
see ``now()`` and ``utcnow()`` returning ``datetime``, ``today()`` returning
``date``, and reject any other clock method. ``_clock: RecordClock``
annotations still type-check, but only describe the live clock.

Clock-aware validation
----------------------

Initialization checks available method source for obvious direct uses such as
``datetime.now()`` and ``date.today()``. Some patterns only warn, and aliases,
helpers, or missing source can escape detection. Passing validation does not
prove deterministic behavior. For tests, install a ``coopy.testing`` clock;
see :doc:`util_api`.
