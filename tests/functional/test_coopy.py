import os
import shutil
import unittest

TEST_DIR = 'coopy_test/'
TEST_DIR_AUX = 'coopynet_test/'


class TestCoopy(unittest.TestCase):
    def setUp(self):
        os.mkdir(TEST_DIR)

    def tearDown(self):
        shutil.rmtree(TEST_DIR)

    def test_coopy(self):
        from ..domain import Wiki
        import coopy.base

        wiki = coopy.base.init_persistent_system(Wiki, basedir=TEST_DIR)

        page_a = wiki.create_page('Home','Welcome', None)
        date_a = page_a.last_modified

        page_b = wiki.create_page('coopy',
                                'http://bitbucket.org/loogica/coopy',
                                page_a)
        date_b = page_b.last_modified

        page_c = wiki.create_page('Test data','0.2', page_a)
        date_c = page_c.last_modified
        wiki.close()

        new_wiki = coopy.base.init_persistent_system(Wiki(), basedir=TEST_DIR)

        self.assertEqual('Home', new_wiki.get_page('Home').id)
        self.assertEqual('Welcome', new_wiki.get_page('Home').content)

        self.assertEqual('coopy', new_wiki.get_page('coopy').id)
        self.assertEqual('http://bitbucket.org/loogica/coopy',
                         new_wiki.get_page('coopy').content)

        self.assertEqual('Test data', new_wiki.get_page('Test data').id)
        self.assertEqual('0.2', new_wiki.get_page('Test data').content)

        self.assertEqual(date_a, new_wiki.get_page('Home').last_modified)
        self.assertEqual(date_b, new_wiki.get_page('coopy').last_modified)
        self.assertEqual(date_c, new_wiki.get_page('Test data').last_modified)
        new_wiki.close()

    def test_coopy_multiple_calls_now(self):
        from ..domain import Wiki
        import coopy.base

        wiki = coopy.base.init_persistent_system(Wiki, basedir=TEST_DIR)

        wiki.multiple_call_now()
        dt1 = wiki.dt1
        dt2 = wiki.dt2

        wiki.close()
        new_wiki = coopy.base.init_persistent_system(Wiki(), basedir=TEST_DIR)

        self.assertEqual(dt1, new_wiki.dt1)
        self.assertEqual(dt2, new_wiki.dt2)

        new_wiki.close()

    def test_bad_system(self):
        '''
            Because calls to datetime.{now(),utcnow()} or to date.today()
            aren't allowed. Use the clock:
            http://coopy.readthedocs.org/en/latest/use_clock.html
        '''
        from ..domain import Wiki
        import coopy.base
        from coopy.error import PrevalentError

        class BadWiki(Wiki):
            def bad_method(self):
                from datetime import date
                dt = date.today()

        self.assertRaises(PrevalentError,
                          coopy.base.init_persistent_system,
                              *[BadWiki], **dict(basedir=TEST_DIR))

    def test_enable_clock(self):
        from coopy.tests.utils import TestSystemMixin
        class DummyWiky():
            def __init__(self):
                pass

        dummy_wiki = DummyWiky()
        assert not hasattr(dummy_wiki, '_clock')
        TestSystemMixin().enable_clock(dummy_wiki)
        assert hasattr(dummy_wiki, '_clock')


    def test_mock_clock(self):
        import datetime
        from coopy.tests.utils import TestSystemMixin
        class DummyWiky():
            def __init__(self):
                pass

        dt = datetime.datetime.now()
        dummy_wiki = DummyWiky()
        assert not hasattr(dummy_wiki, '_clock')
        TestSystemMixin().mock_clock(dummy_wiki, dt)
        assert hasattr(dummy_wiki, '_clock')
        assert dt == dummy_wiki._clock.now()
