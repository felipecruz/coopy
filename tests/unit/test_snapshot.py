import os
import unittest
import shutil
from coopy.snapshot import *

TEST_DIR = 'snapshot_test'

class TestSnapshot(unittest.TestCase):
    
    def setUp(self):
        os.mkdir(TEST_DIR)

    def tearDown(self):
        shutil.rmtree(TEST_DIR)

    def test_take_snapshot(self):
        mock = 'test object'
        manager = SnapshotManager(TEST_DIR)
        manager.take_snapshot(mock)
        self.assertEqual(len(os.listdir(TEST_DIR)), 1)
        self.assertTrue(os.listdir(TEST_DIR)[0].endswith('dat'))
        
    def test_recover_snapshot(self):
        mock = 'test object'
        manager = SnapshotManager(TEST_DIR)
        manager.take_snapshot(mock)
        result = manager.recover_snapshot()
        self.assertEqual(result, mock)


if __name__ == '__main__':
    unittest.main()
