import pytest
import socket

from coopy.network import COPYNET_HEADER
from coopy.network.default_select import CopyNet

def tcp_actor(address, port, _type):
    if _type == "inet":
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
        s.connect((address, port))
    else:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) 
        s.connect(address)
    s.setblocking(0)
    return s

def test_network_select_init():
    system = "a string represented system state"

    copynet = CopyNet(system)

    assert isinstance(copynet.server, socket.socket) 
    assert len(copynet.clientmap) == 0
    assert copynet.outputs == []
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
    with pytest.raises(socket.error):
        select.select([copynet.server], [], [], 0)

#@pytest.skip
def test_network_select_receive():
    from coopy.base import logging_config

    logging_config(basedir="./")

    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()
    
    actor = tcp_actor("127.0.0.1", 7777, "inet")
    actor.send('copynet')
 
    #guarantee that the client is already connected
    import time
    time.sleep(0.2)
    
    copynet.receive("message")
   
    #if no error, socket is open
    import select
    select.select([], [], [actor], 0)

    import struct, zlib, cPickle
    size = struct.calcsize(COPYNET_HEADER)
    header = actor.recv(size)
    (psize, stype) = struct.unpack(COPYNET_HEADER, header)
    data = cPickle.loads(zlib.decompress(actor.recv(psize)))

    assert stype == 's'
    assert data == "message"

    copynet.close()
    actor.close()

def test_network_select_disconnect_senders():
    from coopy.base import logging_config

    logging_config(basedir="./")

    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()
    
    actor = tcp_actor("127.0.0.1", 7777, "inet")
    actor.send('copynet')
 
    #guarantee that the client is already connected
    import time
    time.sleep(0.2)
    
    actor.send('actor should be disconnected')
    time.sleep(0.2)
   
    assert 0 == len(copynet.clientmap)
    assert 0 == len(copynet.outputs)

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
    actor1.send('copynet')
    
    actor2 = tcp_actor("127.0.0.1", 7777, "inet")
    actor2.send('copynet')

    clients = [actor1, actor2]
 
    #guarantee that the client is already connected
    import time
    time.sleep(0.2)
    
    copynet.receive("message")
   
    #if no error, socket is open
    import select
    select.select(clients, clients, clients, 0)

    #both clients should receive the same message
    for cli in clients:
        import struct, zlib, cPickle
        size = struct.calcsize(COPYNET_HEADER)
        header = cli.recv(size)
        (psize, stype) = struct.unpack(COPYNET_HEADER, header)
        data = cPickle.loads(zlib.decompress(cli.recv(psize)))
        received_msgs.append(data)

        assert stype == 's'
        assert data == "message"

    assert len(received_msgs) == 2
    assert received_msgs == ["message", "message"]

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
    actor1.send('copynet')
    
    actor2 = tcp_actor("127.0.0.1", 7777, "inet")
    actor2.send('copynet')

    actors = [actor1, actor2]

    #guarantee that the client is already connected
    import time
    time.sleep(0.2)
    
    copynet_client1 = copynet.clientmap.values()[0]
    copynet.send_direct(copynet_client1.client, "message")

    time.sleep(0.2)

    import struct, zlib, cPickle
    size = struct.calcsize(COPYNET_HEADER)
    
    #one of the 2 reads will raise an error and the other will work
    error_count = 0
    
    for actor in actors:
        try:
            header = actor.recv(size)
            (psize, stype) = struct.unpack(COPYNET_HEADER, header)
            data = cPickle.loads(zlib.decompress(actor.recv(psize)))
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
    actor1.send('copynet')
    
    #guarantee that the client is already connected
    import time
    time.sleep(0.2)
    
    copynet_client1 = copynet.clientmap.values()[0]
    actor1.send('copynet')
    assert True == copynet.check_if_authorized_client(copynet_client1.client)
    
    actor1.close()

    actor2 = tcp_actor("127.0.0.1", 7777, "inet")
    actor2.send('copynet')
    
    time.sleep(0.2)

    copynet_client2 = copynet.clientmap.values()[0]
    actor2.send('_copynet')
    assert False == copynet.check_if_authorized_client(copynet_client2.client)

    actor2.close()
    copynet.close()
