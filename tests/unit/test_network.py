import unittest
from ..domain import Wiki

class TestNetwork(unittest.TestCase):
    def test_prepare_data(self):
        from coopy.network import prepare_data
        from coopy.foundation import RecordClock
        from coopy.utils import inject
        import cPickle
        import zlib

        wiki = Wiki()
        inject(wiki, '_clock', RecordClock())
        wiki.create_page('test', 'test content', None)

        (header, compressed_data) = prepare_data(wiki)

        copy_wiki = cPickle.loads(zlib.decompress(compressed_data))

        self.assertEquals('test',copy_wiki.get_page('test').id)
        self.assertEquals('test content',copy_wiki.get_page('test').content)
    
    def test_prepare_action_data(self):
        from coopy.foundation import Action
        from coopy.network import prepare_data
        import cPickle
        import zlib
        import datetime
        
        args = []
        kwargs = {}

        action = Action('caller_id', 
                        'test', 
                        datetime.datetime.now(), 
                        args, 
                        kwargs
                    )

        (header, compressed_data) = prepare_data(action)

        copy_action = cPickle.loads(zlib.decompress(compressed_data))

        self.assertEquals(action.caller_id, copy_action.caller_id)
        self.assertEquals(action.action, copy_action.action)
        self.assertEquals(action.args, copy_action.args)
        self.assertEquals(action.kwargs, copy_action.kwargs)
        self.assertEquals(action.timestamps, copy_action.timestamps)
