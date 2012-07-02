import unittest
from ..domain import Wiki

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

if __name__ == "__main__":
    unittest.main()
