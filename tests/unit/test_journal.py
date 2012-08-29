import six
import unittest

import os
import shutil

from coopy.journal import DiskJournal

JOURNAL_DIR = 'journal_test/'

class TestJournal(unittest.TestCase):
    def setUp(self):
        os.mkdir(JOURNAL_DIR)

    def tearDown(self):
        shutil.rmtree(JOURNAL_DIR)

    def test_current_journal_file(self):
        journal = DiskJournal(JOURNAL_DIR)
        expected_file_name = '%s%s' % (JOURNAL_DIR,
                                      'transaction_000000000000002.log')

        self.assertEquals(expected_file_name,
                          journal.current_journal_file(JOURNAL_DIR).name)

        # test hack! - create next file
        new_file_name = expected_file_name.replace('2','3')
        open(new_file_name, 'wt').close()

        self.assertEquals(new_file_name,
                          journal.current_journal_file(JOURNAL_DIR).name)

    def test_receive(self):
        import pickle
        class Message(object):
            def __init__(self, value):
                self.value = value
            def __getstate__(self):
                raise pickle.PicklingError()

        message = Message('test message')
        journal = DiskJournal(JOURNAL_DIR)
        journal.setup()

        self.assertRaises(
                            pickle.PicklingError,
                            journal.receive,
                            (message)
                          )

    def test_close(self):
        journal = DiskJournal(JOURNAL_DIR)
        self.assertTrue(not journal.file)

        journal.setup()
        self.assertTrue(not journal.file.closed)

        journal.close()
        self.assertTrue(journal.file.closed)

    def test_setup(self):
        journal = DiskJournal(JOURNAL_DIR)
        self.assertEquals(JOURNAL_DIR, journal.basedir)

        journal.setup()
        expected_file_name = '%s%s' % (JOURNAL_DIR,
                                      'transaction_000000000000002.log')
        self.assertEquals(expected_file_name,
                          journal.file.name)

        if six.PY3:
            import pickle
        else:
            import cPickle as pickle
        # test hack
        pickle_class = pickle.Pickler(open(expected_file_name, 'rb'))\
                                                            .__class__
        self.assertTrue(isinstance(journal.pickler, pickle_class))

