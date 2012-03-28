import os
import unittest
import shutil
import coopy
import coopy.fileutils as fu
from ..domain import Wiki

TEST_DIR = 'fileutils_test/'

class TestFileUtils(unittest.TestCase):
    
    def setUp(self):
        os.mkdir(TEST_DIR)

    def tearDown(self):
        shutil.rmtree(TEST_DIR)
    
    def test_number_as_string(self):
        self.assertEqual(fu.number_as_string(0),'000000000000000')
        self.assertEqual(fu.number_as_string(1),'000000000000001')
        self.assertEqual(fu.number_as_string(10),'000000000000010')
        self.assertEqual(fu.number_as_string(11),'000000000000011')

    def test_list_snapshot_files(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.list_snapshot_files(TEST_DIR)
        self.assertEqual(1, len(result))   
    
    def test_list_log_files(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.list_log_files(TEST_DIR)
        self.assertEqual(4, len(result))
        
    def test_last_snapshot_file(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.last_snapshot_file(TEST_DIR)
        self.assertEqual('snapshot_000000000000004.dat',result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.last_snapshot_file(TEST_DIR)
        self.assertEqual('snapshot_000000000000006.dat',result)
        
    
    def test_last_log_file(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.last_log_file(TEST_DIR)
        self.assertEqual('transaction_000000000000005.log',result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.last_log_file(TEST_DIR)
        self.assertEqual('transaction_000000000000005.log',result)

    def test_lastest_snapshot_number(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.lastest_snapshot_number(TEST_DIR)
        self.assertEqual(4,result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.lastest_snapshot_number(TEST_DIR)
        self.assertEqual(6,result)
        

    def test_lastest_log_number(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.lastest_log_number(TEST_DIR)
        self.assertEqual(5,result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.lastest_log_number(TEST_DIR)
        self.assertEqual(5,result)
        
    def test_to_log_file(self):
        result = fu.to_log_file(TEST_DIR, 1)
        self.assertEqual(TEST_DIR + 'transaction_000000000000001.log', result)
        
    def test_to_snapshot_file(self):
        result = fu.to_snapshot_file(TEST_DIR, 1)
        self.assertEqual(TEST_DIR + 'snapshot_000000000000001.dat' , result)
        
    def test_get_number(self):
        result = fu.get_number('transaction_000000000000001.log')
        self.assertEqual(1,result)
        result = fu.get_number('transaction_000000000000010.log')
        self.assertEqual(10,result)
        result = fu.get_number('snapshot_000000000000001.dat')
        self.assertEqual(1,result)
        result = fu.get_number('snapshot_000000000000010.dat')
        self.assertEqual(10,result)
        
    def test_next_number(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        result = fu.next_number(TEST_DIR)
        self.assertEqual(2, result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.next_number(TEST_DIR)
        self.assertEqual(6, result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.next_number(TEST_DIR)
        self.assertEqual(7, result)

    def test_next_snapshot_file(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        result = fu.next_snapshot_file(TEST_DIR)
        self.assertEqual(TEST_DIR + 'snapshot_000000000000002.dat', result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.next_snapshot_file(TEST_DIR)
        self.assertEqual(TEST_DIR + 'snapshot_000000000000006.dat', result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.next_snapshot_file(TEST_DIR)
        self.assertEqual(TEST_DIR + 'snapshot_000000000000007.dat', result)
        
    def test_next_log_file(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        result = fu.next_log_file(TEST_DIR)
        self.assertEqual(TEST_DIR + 'transaction_000000000000002.log', result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.next_log_file(TEST_DIR)
        self.assertEqual(TEST_DIR + 'transaction_000000000000006.log', result)
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.next_log_file(TEST_DIR)
        self.assertEqual(TEST_DIR + 'transaction_000000000000007.log', result)

    def test_last_log_files(self):
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        result = fu.last_log_files(TEST_DIR)
        self.assertEqual(1, len(result))
        self.assertEqual(TEST_DIR + 'transaction_000000000000005.log', result[0])
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        result = fu.last_log_files(TEST_DIR)
        self.assertEqual(0, len(result))
        
        self.tearDown()
        self.setUp()
        
        open(TEST_DIR + 'transaction_000000000000001.log', 'w')
        open(TEST_DIR + 'transaction_000000000000002.log', 'w')
        open(TEST_DIR + 'transaction_000000000000003.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000004.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000005.log', 'w')
        open(TEST_DIR + 'snapshot_000000000000006.dat', 'w')
        open(TEST_DIR + 'transaction_000000000000007.log', 'w')
        open(TEST_DIR + 'transaction_000000000000008.log', 'w')
        result = fu.last_log_files(TEST_DIR)
        self.assertEqual(2, len(result))
        self.assertEqual(TEST_DIR + 'transaction_000000000000007.log', result[0])
        self.assertEqual(TEST_DIR + 'transaction_000000000000008.log', result[1])
        
    def test_snapshot_init(self):
        manager = fu.name_to_dir('')
        self.assertEqual(manager, './')
        
        manager = fu.name_to_dir('.')
        self.assertEqual(manager, './')
        
        manager = fu.name_to_dir('app')
        self.assertEqual(manager, 'app/')
        
        manager = fu.name_to_dir('app/')
        self.assertEqual(manager, 'app/')
        
        manager = fu.name_to_dir('app\\')
        self.assertEqual(manager, 'app/')
        
        manager = fu.name_to_dir('app\\app\\')
        self.assertEqual(manager, 'app/app/')
        
        manager = fu.name_to_dir('app\\app')
        self.assertEqual(manager, 'app/app/')

        manager = fu.name_to_dir('app/app')
        self.assertEqual(manager, 'app/app/')
        
        manager = fu.name_to_dir('app/app/')
        self.assertEqual(manager, 'app/app/')

    def test_obj_to_dir_name(self):
        result = fu.obj_to_dir_name(Wiki)
        self.assertEqual('wiki',result)
        result = fu.obj_to_dir_name(Wiki())
        self.assertEqual('wiki',result)
        result = fu.obj_to_dir_name("string")
        self.assertEqual('str',result)


if __name__ == '__main__':
    unittest.main()
