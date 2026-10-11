.. _util_api:

Utilitary API
=============

There are some utilitary methods to help you.

Given::

    from coopy.base import init_persistent_system
    from wiki import Wiki  # the tutorial domain

    wiki = init_persistent_system(Wiki, basedir="wiki-data")
    try:
        paths = wiki.basedir_abspath()
    finally:
        wiki.close()


.. function:: basedir_abspath()

    Return a list with all basedirs absolute paths


Test clocks
-----------

If your domain uses the :doc:`use_clock` feature, ``coopy.testing`` provides
deterministic clocks that implement ``coopy.Clock``, so time-dependent rules
are tested without sleeping:

``FrozenClock(dt)``
    ``now()`` and ``utcnow()`` always return ``dt``; ``today()`` returns
    ``dt.date()``. ``now(tz)`` converts an aware ``dt`` to ``tz`` and attaches
    ``tz`` to a naive one. ``time()`` returns ``dt.timestamp()`` (naive ``dt``
    counts as local time) and ``monotonic()`` stays at ``0.0``.

``ManualClock(start)``
    Like ``FrozenClock`` but movable: ``advance(timedelta)`` moves forward
    (negative deltas raise ``ValueError``) and ``set(dt)`` jumps anywhere.
    ``monotonic()`` adds up the ``advance()`` deltas and ignores ``set()``.

``install_clock(system, clock)``
    On a system returned by ``coopy.open``, later method calls read
    ``self._clock`` from ``clock``. The values are journaled like real clock
    values, so they replay after a restart and on replicas; the test clock
    itself is never stored in snapshots. On a plain domain object ``clock`` is
    injected as ``_clock`` directly. ``install_clock(system, None)`` restores
    the real clock.

A token that expires after one hour::

    from datetime import datetime, timedelta

    import coopy
    from coopy.decorators import readonly
    from coopy.testing import ManualClock, install_clock


    class Tokens:
        _clock: coopy.Clock

        def __init__(self) -> None:
            self.issued: dict[str, datetime] = {}

        def issue(self, name: str) -> None:
            self.issued[name] = self._clock.now()

        @readonly
        def is_valid(self, name: str) -> bool:
            return self._clock.now() - self.issued[name] < timedelta(hours=1)


    def test_token_expires_after_one_hour(tmp_path):
        clock = ManualClock(datetime(2026, 1, 1, 12))
        with coopy.control(coopy.open(Tokens, basedir=str(tmp_path))) as tokens:
            install_clock(tokens, clock)
            tokens.issue("abc")
            clock.advance(timedelta(minutes=59))
            assert tokens.is_valid("abc")
            clock.advance(timedelta(minutes=1))
            assert not tokens.is_valid("abc")

Test environments
~~~~~~~~~~~~~~~~~

Domains using :doc:`use_env` are tested with a seeded environment:

``SeededEnv(seed=0)``
    Implements ``coopy.Env`` with every value drawn from
    ``random.Random(seed)``: the same seed gives the same numbers, UUIDs and
    tokens. Its tokens are predictable; use it only in tests.

``install_env(system, env)``
    Like ``install_clock``: later calls on a system returned by
    ``coopy.open`` record the values ``env`` returns, so they replay after a
    restart and on replicas; ``env`` itself is never stored. On a plain
    domain object ``env`` is injected as ``_env`` directly.
    ``install_env(system, None)`` restores OS entropy.

::

    from coopy.testing import SeededEnv, install_env


    def draw(directory, seed):
        with coopy.control(coopy.open(Raffle, basedir=directory)) as raffle:
            install_env(raffle, SeededEnv(seed))
            tickets = [raffle.enter(name) for name in ("ana", "bo", "cy")]
            return tickets, raffle.draw()


    def test_draw_is_reproducible(tmp_path):
        assert draw(str(tmp_path / "a"), 7) == draw(str(tmp_path / "b"), 7)

Deprecated helpers
~~~~~~~~~~~~~~~~~~

``coopy.tests.utils.TestClock(date)`` and ``TestSystemMixin`` still work but
emit ``DeprecationWarning`` and will be removed in v0.9.
``TestSystemMixin.mock_clock(system, date)`` now calls ``install_clock`` with a
clock returning ``date`` from every method (as before, ``today()`` returns the
value unchanged) and ``enable_clock(system)`` calls
``install_clock(system, None)``. Replace them with ``FrozenClock`` and
``install_clock``.

.. toctree::
   :maxdepth: 1

   modern-api
