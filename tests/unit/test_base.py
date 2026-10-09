import os
import unittest
from unittest import mock

import pytest

from coopy.decorators import abort_exception, readonly

from ..domain import Wiki


class FalseyError(ValueError):
    def __bool__(self):
        return False


@pytest.mark.parametrize('decorators, success_events, failure_events', [
    ((), ['receive_before', 'receive'],
     ['receive_before', 'receive_exception', 'receive']),
    ((abort_exception,), ['receive_before', 'receive'], ['receive_before']),
    ((readonly,), [], ['receive_exception']),
    ((readonly, abort_exception), [], []),
    ((abort_exception, readonly), [], []),
], ids=['ordinary', 'abort', 'readonly', 'readonly-abort', 'abort-readonly'])
@pytest.mark.parametrize('error_type', [None, ValueError, FalseyError],
                         ids=['success', 'failure', 'falsey-exception'])
def test_proxy_publication_by_outcome_and_decorators(
        decorators, success_events, failure_events, error_type):
    from coopy.base import CoopyProxy

    error = error_type('rejected') if error_type is not None else None

    class Domain:
        def call(self, value, *, suffix):
            result = value + suffix
            if error is not None:
                raise error
            return result

    for decorator in decorators:
        Domain.call = decorator(Domain.call)
    subscriber = mock.Mock()
    proxy = CoopyProxy(Domain(), [subscriber])
    try:
        if error is None:
            assert proxy.call('value', suffix='!') == 'value!'
        else:
            with pytest.raises(error_type) as caught:
                proxy.call('value', suffix='!')
            assert caught.value is error

        expected = success_events if error is None else failure_events
        assert [call[0] for call in subscriber.mock_calls] == expected
        if 'receive' in expected:
            action = subscriber.receive.call_args.args[0]
            assert action.action == 'call'
            assert action.args == ('value',)
            assert action.kwargs == {'suffix': '!'}
            assert action.raised is (error is not None)

        # Releasing an unowned RLock raises, verifying cleanup on both paths.
        with pytest.raises(RuntimeError):
            proxy.lock.release()
    finally:
        proxy.close()


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

        self.assertEqual(dummy.__class__, CoopyProxy)
        self.assertEqual(dummy.publisher.subscribers, dummy_subscribers)



    def test_base_persistent(self):
        import os
        from coopy.base import init_persistent_system, CoopyProxy

        dummy = init_persistent_system(Wiki, basedir='wiki/')

        files = os.listdir('wiki/')
        self.assertTrue('snapshot_000000000000002.dat' in files)
        self.assertEqual(dummy.__class__, CoopyProxy)
        self.assertEqual(len(dummy.publisher.subscribers), 1)

        dummy.close()

    def test_base_basedir_abspath(self):
        import os
        import tempfile
        from coopy.base import init_system, init_persistent_system, CoopyProxy
        from coopy.journal import DiskJournal

        dummy = init_persistent_system(Wiki, basedir='wiki/')

        current_dir = os.path.abspath(os.getcwd())
        self.assertEqual([current_dir + "/wiki"],
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
        proxy.start_primary()

        self.assertTrue(hasattr(proxy, 'server'))
        self.assertTrue(proxy.server in proxy.publisher.subscribers)
        proxy.shutdown()
        proxy.close()

    def test_coopyproxy_master_accepts_writes(self):
        from coopy.base import CoopyProxy
        from coopy.utils import inject
        from coopy.foundation import RecordClock

        wiki = Wiki()
        inject(wiki, '_clock', RecordClock())
        proxy = CoopyProxy(wiki, [])
        proxy.start_primary(port=8013)

        proxy.create_page('id', 'content', None)
        self.assertEqual('content', proxy.get_page('id').content)

        server = proxy.master
        proxy.shutdown()
        self.assertTrue(proxy.master is None)
        self.assertFalse(server.running)
        proxy.close()

    def test_coopyproxy_start_snapshot_manager_does_not_block(self):
        import time
        from coopy.base import CoopyProxy

        proxy = CoopyProxy(Wiki(), [])
        start = time.perf_counter()
        proxy.start_snapshot_manager(10)
        self.assertTrue(time.perf_counter() - start < 1)
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
                          proxy.start_replica,
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

        self.assertEqual(1, len(publisher.messages))

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

        proxy.lock.reset_mock()
        proxy.unlocked_method()
        proxy.lock.acquire.assert_not_called()
        proxy.close()

    def test_coopyproxy_take_snapshot(self):
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

        # mock testing
        proxy.lock = mock.MagicMock()
        proxy.create_page('id', 'content', None)

        proxy.take_snapshot()

        proxy.lock.acquire.assert_called()
        proxy.lock.release.assert_called()
        proxy.close()

if __name__ == "__main__":
    unittest.main()
