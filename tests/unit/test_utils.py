import unittest
from coopy import utils

class UtilsTest(unittest.TestCase):

    def test_attribute_access(self):
        class Dummy(object):
            def __init__(self, some_property):
                self.some_property = some_property

            @property
            def check_property(self):
                return self.some_property

            def business_method(self, args):
                return 1

        dummy = Dummy('property')

        self.assertTrue(not 
                        utils.method_or_none(dummy,'some_property'))

        self.assertTrue(not 
                        utils.method_or_none(dummy,'check_property'))
        
        self.assertTrue(utils.method_or_none(dummy,'business_method'))

    def test_action_check(self):
        from coopy.decorators import readonly, unlocked, abort_exception

        def no_decorator():
            pass

        @readonly
        def read_method():
            pass
        
        @unlocked
        def not_locked():
            pass

        @abort_exception
        def abort_on_exception():
            pass

        @readonly
        @unlocked
        def readonly_unlocked():
            pass

        self.assertEquals(
                (False, False, False),
                utils.action_check(no_decorator)
        )
        
        self.assertEquals(
                (True, False, False),
                utils.action_check(read_method)
        )
        
        self.assertEquals(
                (False, True, False),
                utils.action_check(not_locked)
        )

        self.assertEquals(
                (False, False, True),
                utils.action_check(abort_on_exception)
        )

        self.assertEquals(
                (True, True, False),
                utils.action_check(readonly_unlocked)
        )
