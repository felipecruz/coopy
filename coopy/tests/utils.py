from coopy.utils import inject
from coopy.foundation import RecordClock

class TestClock(object):
    def __init__(self, date):
        self.date = date

    def now(self):
        return self.date

    def utcnow(self):
        return self.date

    def today(self):
        return self.date

class TestSystemMixin(object):
    def enable_clock(self, system):
        inject(system, '_clock', RecordClock())

    def mock_clock(self, system, date):
        test_clock = TestClock(date)
        inject(system, '_clock', test_clock)
