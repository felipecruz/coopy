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
clock calls in the same order. Changing domain code or branches can consume
the recorded results incorrectly. Randomness and external I/O are not captured
by this clock; see :doc:`usage`.

Clock-aware validation
----------------------

Initialization checks available method source for obvious direct uses such as
``datetime.now()`` and ``date.today()``. Some patterns only warn, and aliases,
helpers, or missing source can escape detection. Passing validation does not
prove deterministic behavior. For isolated domain tests, inject a test clock;
see :doc:`util_api`.
