"""Deprecated test helpers; use :mod:`coopy.testing` instead."""

import warnings

from coopy.testing import install_clock


def _deprecated(old, new):
    warnings.warn(
        f"coopy.tests.utils.{old} is deprecated; use coopy.testing.{new} (removal: v0.9)",
        DeprecationWarning,
        stacklevel=3,
    )


class TestClock(object):
    """Deprecated: use ``coopy.testing.FrozenClock``."""

    __test__ = False  # not a pytest test class

    def __init__(self, date):
        _deprecated("TestClock", "FrozenClock")
        self.date = date

    def now(self):
        return self.date

    def utcnow(self):
        return self.date

    def today(self):
        return self.date


class TestSystemMixin(object):
    """Deprecated: use ``coopy.testing.install_clock``."""

    __test__ = False  # not a pytest test class

    def enable_clock(self, system):
        _deprecated("TestSystemMixin.enable_clock", "install_clock(system, None)")
        install_clock(system, None)

    def mock_clock(self, system, date):
        _deprecated("TestSystemMixin.mock_clock", "install_clock(system, FrozenClock(dt))")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            test_clock = TestClock(date)
        install_clock(system, test_clock)
