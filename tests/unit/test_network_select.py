import six
import sys
import pytest
import socket

from coopy.network.network import COPYNET_HEADER
from coopy.network.default_select import CopyNet, CopyNetSlave, _HEADER_SIZE

_str_to_bytes = lambda x: x.encode('utf-8') if type(x) != bytes else x

if six.PY3 or 'PyPy' in sys.version:
    socket_select_error = ValueError
else:
    socket_select_error = socket.error

def tcp_actor(address, port, _type):
    if _type == "inet":
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((address, port))
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(address)
    s.setblocking(0)
    return s

def tcp_server(address, port, _type, max_clients=5):
    if _type == "inet":
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((address, port))
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(address)
    s.listen(max_clients)
    s.setblocking(0)
    return s

def test_network_select_init():
    system = "a string represented system state"

    copynet = CopyNet(system)

    assert isinstance(copynet.server, socket.socket)
    assert len(copynet.clientmap) == 0
    assert copynet.queues == {}
    assert copynet.obj == system

    copynet.close()

def test_network_select_init_close():
    import select
    system = "a string represented system state"

    copynet = CopyNet(system)

    #no error because socket is open
    select.select([copynet.server], [], [], 0)

    copynet.close()

    assert copynet.running == False

    #must raise error
    with pytest.raises(socket_select_error):
        select.select([copynet.server], [], [], 0)

#@pytest.skip
def test_network_select_receive():
    from coopy.base import logging_config

    logging_config(basedir="./")

    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()

    actor = tcp_actor("127.0.0.1", 7777, "inet")
    actor.send(b'copynet')

    #guarantee that the client is already connected
    import time
    time.sleep(0.2)

    copynet.receive(b"message")

    #if no error, socket is open
    import select
    select.select([], [], [actor], 0)

    import struct, zlib
    if six.PY3:
        import pickle
    else:
        import cPickle as pickle

    size = struct.calcsize(COPYNET_HEADER)
    header = actor.recv(size)
    (psize, stype) = struct.unpack(COPYNET_HEADER, header)
    data = pickle.loads(zlib.decompress(actor.recv(psize)))

    assert stype == b's'
    assert data == b"message"

    copynet.close()
    actor.close()

def test_network_select_disconnect_senders():
    from coopy.base import logging_config

    logging_config(basedir="./")

    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()

    actor = tcp_actor("127.0.0.1", 7777, "inet")
    actor.send(_str_to_bytes('copynet'))

    #guarantee that the client is already connected
    import time
    time.sleep(0.2)

    actor.send(_str_to_bytes('actor should be disconnected'))
    time.sleep(0.2)

    assert 0 == len(copynet.clientmap)

    copynet.close()
    actor.close()

def test_network_select_broadcast():
    received_msgs = []
    from coopy.base import logging_config

    logging_config(basedir="./")

    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()

    actor1 = tcp_actor("127.0.0.1", 7777, "inet")
    actor1.send(_str_to_bytes('copynet'))

    actor2 = tcp_actor("127.0.0.1", 7777, "inet")
    actor2.send(_str_to_bytes('copynet'))

    clients = [actor1, actor2]

    #guarantee that the client is already connected
    import time
    time.sleep(0.2)

    copynet.receive(b"message")
    if six.PY3:
        import pickle
    else:
        import cPickle as pickle

    #both clients should receive the same message
    for cli in clients:
        import struct, zlib, pickle
        size = struct.calcsize(COPYNET_HEADER)
        header = cli.recv(size)
        (psize, stype) = struct.unpack(COPYNET_HEADER, header)
        data = pickle.loads(zlib.decompress(cli.recv(psize)))
        received_msgs.append(data)

        assert stype == b's'
        assert data == b"message"

    assert len(received_msgs) == 2
    assert received_msgs == [b"message", b"message"]

    copynet.close()
    actor1.close()
    actor2.close()

def test_network_select_send_direct():
    received_msgs = []
    from coopy.base import logging_config

    logging_config(basedir="./")

    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()

    actor1 = tcp_actor("127.0.0.1", 7777, "inet")
    actor1.send(_str_to_bytes('copynet'))

    actor2 = tcp_actor("127.0.0.1", 7777, "inet")
    actor2.send(_str_to_bytes('copynet'))

    actors = [actor1, actor2]

    #guarantee that the client is already connected
    import time
    time.sleep(0.2)

    copynet_client1 = list(copynet.clientmap.values())[0]
    copynet.send_direct(copynet_client1.client, _str_to_bytes("message"))

    time.sleep(0.2)

    if six.PY3:
        import pickle
    else:
        import cPickle as pickle
    import struct, zlib, pickle
    size = struct.calcsize(COPYNET_HEADER)

    #one of the 2 reads will raise an error and the other will work
    error_count = 0

    for actor in actors:
        try:
            header = actor.recv(size)
            (psize, stype) = struct.unpack(COPYNET_HEADER, header)
            data = pickle.loads(zlib.decompress(actor.recv(psize)))
            received_msgs.append(data)
        except Exception:
            error_count += 1

    assert len(received_msgs) == 1
    assert error_count == 1

    copynet.close()
    actor1.close()
    actor2.close()

def test_network_select_check_if_authorized_client():
    from coopy.base import logging_config

    logging_config(basedir="./")

    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()

    actor1 = tcp_actor("127.0.0.1", 7777, "inet")
    actor1.send(_str_to_bytes('copynet'))

    #guarantee that the client is already connected
    import time
    time.sleep(0.2)

    copynet_client1 = list(copynet.clientmap.values())[0]
    actor1.send(_str_to_bytes('copynet'))
    assert True == copynet.check_if_authorized_client(copynet_client1.client)

    actor1.close()

    actor2 = tcp_actor("127.0.0.1", 7777, "inet")
    actor2.send(_str_to_bytes('copynet'))

    time.sleep(0.2)

    copynet_client2 = list(copynet.clientmap.values())[0]
    actor2.send(_str_to_bytes('_copynet'))
    assert False == copynet.check_if_authorized_client(copynet_client2.client)

    actor2.close()
    copynet.close()

def test_copynetslave_init():
    class mock(object):
        def __init__(self):
            self.value = 0
        def inc(self):
            self.value += 1
            return self.value

    server = tcp_server('127.0.0.1', 5466, "inet")

    system = mock()
    slave = CopyNetSlave(system)

    slave.close()
    assert slave.running == False

    server.close()

def test_copynetslave_disconnect_on_empty_data():
    class mock(object):
        def __init__(self):
            self.value = 0
        def inc(self):
            self.value += 1
            return self.value

    from coopy.base import logging_config

    logging_config()

    server = tcp_server('127.0.0.1', 5466, "inet")

    system = mock()
    slave = CopyNetSlave(system, host='127.0.0.1')
    slave.start()

    import time
    time.sleep(0.2)

    cli, address = server.accept()

    time.sleep(0.2)
    cli.sendall(_str_to_bytes('1'))

    time.sleep(0.2)
    assert slave.running == False

    import select
    with pytest.raises(socket_select_error):
        select.select([slave.sock], [], [], 0)

    server.close()
