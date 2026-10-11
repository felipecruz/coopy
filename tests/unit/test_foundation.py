import unittest


class TestAction(unittest.TestCase):
    def test_execute_action(self):
        from datetime import datetime

        from coopy.foundation import Action, RecordClock
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
        inject(dummy, "_clock", RecordClock())

        action = Action("caller_id", "business_method_noargs", datetime.now(), (), {})

        action.execute_action(dummy)

        self.assertEqual(1, dummy.exec_count)

        action = Action("caller_id", "business_method_args", datetime.now(), ([1]), {})

        action.execute_action(dummy)

        self.assertEqual(3, dummy.exec_count)

        action = Action(
            "caller_id", "business_method_kwargs", datetime.now(), (), {"keyword_arg": "test"}
        )

        action.execute_action(dummy)

        self.assertEqual(6, dummy.exec_count)


class TestRecordClock(unittest.TestCase):
    def test_record_clock(self):
        from coopy.foundation import RecordClock

        clock = RecordClock()
        self.assertTrue(len(clock.results) == 0)

        dt1 = clock.now()
        self.assertEqual(dt1, clock.results[0])

        dt2 = clock.now()
        self.assertEqual(dt2, clock.results[1])

        dt = clock.today()
        self.assertEqual(dt, clock.results[2])

        utcnow = clock.utcnow()
        self.assertEqual(utcnow, clock.results[3])


class TestRestoreClock(unittest.TestCase):
    def test_restore_clock(self):
        from datetime import date, datetime, timezone

        from coopy.foundation import RestoreClock

        dt1 = datetime.now()
        dt2 = date.today()
        dt3 = datetime.now(timezone.utc).replace(tzinfo=None)

        clock = RestoreClock([dt1, dt2, dt3])

        self.assertEqual(dt1, clock.now())
        self.assertEqual(dt2, clock.today())
        self.assertEqual(dt3, clock.utcnow())


class TestClockProtocol(unittest.TestCase):
    def test_public_clock_protocol(self):
        import coopy
        from coopy.foundation import Clock

        self.assertIs(coopy.Clock, Clock)
        self.assertIn("Clock", coopy.__all__)

    def test_clocks_have_no_attribute_fallback(self):
        from coopy.foundation import RecordClock, RestoreClock

        for clock in (RecordClock(), RestoreClock([])):
            self.assertNotIn("__getattr__", type(clock).__dict__)
            with self.assertRaises(AttributeError):
                clock.fromtimestamp  # noqa: B018


if __name__ == "__main__":
    unittest.main()
