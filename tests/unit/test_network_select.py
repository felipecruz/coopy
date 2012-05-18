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
    assert copynet.clients == 0
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
