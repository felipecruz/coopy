from tests.domain import Wiki

def test_prepare_data():
    from coopy.network.network import prepare_data
    from coopy.foundation import RecordClock
    from coopy.utils import inject
    import six
    if six.PY3:
        import pickle
    else:
        import cPickle as pickle
    import zlib

    wiki = Wiki()
    inject(wiki, '_clock', RecordClock())
    wiki.create_page('test', 'test content', None)

    (header, compressed_data) = prepare_data(wiki)

    copy_wiki = pickle.loads(zlib.decompress(compressed_data))

    assert copy_wiki.get_page('test').id == 'test'
    assert copy_wiki.get_page('test').content == 'test content'

def test_prepare_action():
    from coopy.foundation import Action
    from coopy.network.network import prepare_data
    import six
    if six.PY3:
        import pickle
    else:
        import cPickle as pickle
    import zlib
    import datetime

    args = []
    kwargs = {}

    action = Action('caller_id',
                    'test',
                    datetime.datetime.now(),
                    args,
                    kwargs)

    (header, compressed_data) = prepare_data(action)

    copy_action = pickle.loads(zlib.decompress(compressed_data))

    assert action.caller_id == copy_action.caller_id
    assert action.action == copy_action.action
    assert action.args == copy_action.args
    assert action.kwargs == copy_action.kwargs
    assert action.timestamps == copy_action.timestamps
