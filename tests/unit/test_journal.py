import pickle
import six
import os
import shutil
import unittest

try:
    import mock
except:
    from unittest import mock

from coopy.journal import DiskJournal, SecureJournal, verify_sign

JOURNAL_DIR = 'journal_test/'
CURRENT_DIR = os.getcwd()

class TestJournal(unittest.TestCase):
    def setUp(self):
        os.mkdir(JOURNAL_DIR)

    def tearDown(self):
        shutil.rmtree(JOURNAL_DIR)

    def test_current_journal_file(self):
        journal = DiskJournal(JOURNAL_DIR, CURRENT_DIR)
        expected_file_name = '%s%s' % (JOURNAL_DIR,
                                      'transaction_000000000000002.log')

        self.assertEquals(expected_file_name,
                          journal.current_journal_file(JOURNAL_DIR).name)

        # test hack! - create next file
        new_file_name = expected_file_name.replace('2','3')
        open(new_file_name, 'wt').close()

        self.assertEquals(new_file_name,
                          journal.current_journal_file(JOURNAL_DIR).name)

    def test_receive_calls_pickle(self):
        class Message(object):
            def __init__(self, value):
                self.value = value
            def __getstate__(self):
                raise pickle.PicklingError()

        message = Message('test message')
        journal = DiskJournal(JOURNAL_DIR, CURRENT_DIR)
        journal.setup()

        self.assertRaises(pickle.PicklingError, journal.receive, (message))

    def test_receive_calls_pickle_mock(self):
        message = "message"
        name = 'coopy.journal.Pickler'
        pickler_mock = mock.MagicMock()
        journal = DiskJournal(JOURNAL_DIR, CURRENT_DIR)
        journal.setup()
        journal.pickler = pickler_mock
        journal.receive(message)
        pickler_mock.dump.assert_called_with(message)

    def test_securejournal_init(self):
        pickler_mock = mock.MagicMock()
        journal = SecureJournal(JOURNAL_DIR, CURRENT_DIR)
        journal.setup()
        self.assertEqual([], journal.signatures)

    def test_securejoutnal_receive_calls_pickle_mock(self):
        message = "message"
        name = 'coopy.journal.Pickler'
        pickler_mock = mock.MagicMock()
        journal = SecureJournal(JOURNAL_DIR, CURRENT_DIR)
        journal.setup()
        journal.pickler = pickler_mock
        journal.receive(message)
        journal.close()
        signature = open(journal.sig_file_name, "r").read()
        bytes_message = pickler_mock.dump.call_args_list[0][0][0] # UOU! :D
        self.assertTrue(verify_sign("public.key", signature, bytes_message))

    def test_close(self):
        journal = DiskJournal(JOURNAL_DIR, CURRENT_DIR)
        self.assertTrue(not journal.file)

        journal.setup()
        self.assertTrue(not journal.file.closed)

        journal.close()
        self.assertTrue(journal.file.closed)

    def test_setup(self):
        journal = DiskJournal(JOURNAL_DIR, CURRENT_DIR)
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

