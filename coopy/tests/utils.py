from coopy.utils import inject
from coopy.foundation import RecordClock

class TestSystemMixin(object):
    def enable_clock(self, system):
        inject(system, '_clock', RecordClock())
