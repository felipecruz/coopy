import os
import six
import unittest

import pytest

from ..domain import Wiki

if six.PY3:
    from unittest import mock
else:
    import mock

class TestBase(unittest.TestCase):
    def tearDown(self):
        import shutil
        try:
            shutil.rmtree('wiki/')
        except:
            "nothing to do"
            pass

    def test_base(self):
        from coopy.base import init_system, CoopyProxy

        dummy_subscribers = ['a']

        dummy = init_system(Wiki, dummy_subscribers)

        self.assertEquals(dummy.__class__, CoopyProxy)
        self.assertEquals(dummy.publisher.subscribers, dummy_subscribers)



    def test_base_persistent(self):
        import os
        from coopy.base import init_persistent_system, CoopyProxy

        dummy = init_persistent_system(Wiki, basedir='wiki/')

        files = os.listdir('wiki/')
        self.assertTrue('snapshot_000000000000002.dat' in files)
        self.assertEquals(dummy.__class__, CoopyProxy)
        self.assertEquals(len(dummy.publisher.subscribers), 1)

        dummy.close()

    def test_base_basedir_abspath(self):
        import os
        import tempfile
        from coopy.base import init_system, init_persistent_system, CoopyProxy
        from coopy.journal import DiskJournal

        dummy = init_persistent_system(Wiki, basedir='wiki/')

        current_dir = os.path.abspath(os.getcwd())
        self.assertEquals([current_dir + "/wiki/"],
                          dummy.basedir_abspath())

        dummy.close()

        dir1 = tempfile.mkdtemp()
        dir2 = tempfile.mkdtemp()

        j1 = DiskJournal(dir1, os.getcwd())
        j2 = DiskJournal(dir2, os.getcwd())

        subscribers = [j1, j2]

        dummy2 = init_system(Wiki, subscribers)
        self.assertTrue(dir1 in dummy2.basedir_abspath())
        self.assertTrue(dir2 in dummy2.basedir_abspath())


class TestCoopyProxy(unittest.TestCase):
    def tearDown(self):
        import shutil
        try:
            shutil.rmtree('wiki/')
        except:
            "nothing to do"
            pass

    def test_coopyproxy_init(self):
        from coopy.base import CoopyProxy

        import os
        os.mkdir('wiki')

        class PassPublisher(object):
            def close(self):
                pass
            def receive(self):
                pass

        proxy = CoopyProxy(Wiki(), [PassPublisher()])

        self.assertTrue(hasattr(proxy, 'obj'))
        self.assertTrue(hasattr(proxy, 'publisher'))
        self.assertTrue(hasattr(proxy, 'lock'))
        self.assertTrue(hasattr(proxy, 'take_snapshot'))
        self.assertTrue(hasattr(proxy, 'close'))
        self.assertTrue(hasattr(proxy, 'shutdown'))

        proxy.close()

    def test_coopyproxy_start_snapshot_manager(self):
        from coopy.base import CoopyProxy
        import os
        os.mkdir('wiki')

        class PassPublisher(object):
            def close(self):
                pass
            def receive(self):
                pass

        proxy = CoopyProxy(Wiki(), [PassPublisher()])
        proxy.start_snapshot_manager(0)
        self.assertTrue(hasattr(proxy, 'snapshot_timer'))

        proxy.shutdown()
        proxy.close()

    def test_coopyproxy_start_master(self):
        from coopy.base import CoopyProxy
        import os
        os.mkdir('wiki')

        class PassPublisher(object):
            def close(self):
                pass
            def receive(self):
                pass

        proxy = CoopyProxy(Wiki(), [PassPublisher()])
        proxy.start_master()

        self.assertTrue(hasattr(proxy, 'server'))
        self.assertTrue(proxy.server in proxy.publisher.subscribers)
        proxy.shutdown()
        proxy.close()

    def test_coopyproxy_start_slave(self):
        from coopy.base import CoopyProxy

        import os
        os.mkdir('wiki')

        class PassPublisher(object):
            def close(self):
                pass
            def receive(self):
                pass

        proxy = CoopyProxy(Wiki(), [PassPublisher()])

        args = ('localhost', 8012)

        self.assertRaises(Exception,
                          proxy.start_slave,
                          *args)
        proxy.close()

    def test_coopyproxy__getattr__(self):
        from coopy.base import CoopyProxy

        import os
        os.mkdir('wiki')

        class PassPublisher(object):
            def close(self):
                pass
            def receive(self):
                pass

        wiki = Wiki()

        wiki.__dict__['_private'] = "private"
        wiki.__dict__['some_callable'] = lambda x: x

        proxy = CoopyProxy(wiki, [PassPublisher()])

        self.assertTrue(proxy._private == "private")
        self.assertTrue(callable(proxy.some_callable))

        proxy.close()

    def test_coopyproxy_abort_exception(self):
        from coopy.base import CoopyProxy

        import os
        os.mkdir('wiki')

        class PassPublisher(object):
            def __init__(self):
                self.messages = []
            def close(self):
                pass
            def receive(self, message):
                self.messages.append(message)
            def receive_before(self, message):
                self.messages.append(message)
            def receive_exception(self, message):
                self.messages.append(message)


        publisher = PassPublisher()
        proxy = CoopyProxy(Wiki(), [publisher])

        with pytest.raises(Exception):
            proxy.check_abort_exception()

        self.assertEquals(1, len(publisher.messages))

        proxy.close()

    def test_coopyproxy_unlocked(self):
        from coopy.base import CoopyProxy

        import os
        os.mkdir('wiki')

        class PassPublisher(object):
            def close(self):
                pass
            def receive(self, message):
                pass
            def receive_before(self, message):
                pass
            def receive_exception(self, message):
                pass

        proxy = CoopyProxy(Wiki(), [PassPublisher()])
        proxy.create_page('id', 'content', None)

        # we're checking that system remains unlocked after a method execution
        # thus raising a RuntimeError on a release()
        with pytest.raises(RuntimeError):
            proxy.lock.release()


        # mock testing
        proxy.lock = mock.MagicMock()
        proxy.create_page('id', 'content', None)
        proxy.lock.acquire.assert_called_with(1)
        proxy.lock.release.assert_called()

        proxy.unlocked_method()
        proxy.lock.acquire.assert_not_called()
        proxy.close()

if __name__ == "__main__":
    unittest.main()
