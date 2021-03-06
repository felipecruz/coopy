import unittest

class TestAction(unittest.TestCase):
    def test_execute_action(self):
        from coopy.foundation import Action, RecordClock
        from datetime import datetime
        from coopy.utils import inject

        class Dummy(object):
            def __init__(self):
                self.exec_count = 0

            def business_method_noargs(self):
                self.exec_count += 1

            def business_method_args(self, arg):
                self.exec_count += 2

            def business_method_kwargs(self, keyword_arg="test"):
                self.exec_count += 3


        dummy = Dummy()
        # force clock into dummy
        inject(dummy, '_clock', RecordClock())

        action = Action('caller_id',
                        'business_method_noargs',
                        datetime.now(),
                        (),
                        {})

        action.execute_action(dummy)

        self.assertEquals(1, dummy.exec_count)

        action = Action('caller_id',
                        'business_method_args',
                        datetime.now(),
                        ([1]),
                        {})

        action.execute_action(dummy)

        self.assertEquals(3, dummy.exec_count)

        action = Action('caller_id',
                        'business_method_kwargs',
                        datetime.now(),
                        (),
                        {'keyword_arg' : 'test'})

        action.execute_action(dummy)

        self.assertEquals(6, dummy.exec_count)

class TestRecordClock(unittest.TestCase):
    def test_record_clock(self):
        from coopy.foundation import RecordClock

        clock = RecordClock()
        self.assertTrue(len(clock.results) == 0)

        dt1 = clock.now()
        self.assertEquals(dt1, clock.results[0])

        dt2 = clock.now()
        self.assertEquals(dt2, clock.results[1])

        dt = clock.today()
        self.assertEquals(dt, clock.results[2])

        utcnow = clock.utcnow()
        self.assertEquals(utcnow, clock.results[3])

class TestRestoreClock(unittest.TestCase):
    def test_restore_clock(self):
        from coopy.foundation import RestoreClock
        from datetime import datetime, date

        dt1 = datetime.now()
        dt2 = date.today()
        dt3 = datetime.utcnow()

        clock = RestoreClock([dt1, dt2, dt3])

        self.assertEquals(dt1, clock.now())
        self.assertEquals(dt2, clock.today())
        self.assertEquals(dt3, clock.utcnow())

if __name__ == "__main__":
    unittest.main()
