import pytest
import socket

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
    copynet.close()

    assert copynet.running == False

    with pytest.raises(socket.error):
        select.select([copynet.server], [], [], 0)

@pytest.skip
def test_network_select_receive():
    system = "a string represented system state"

    copynet = CopyNet(system, host="127.0.0.1", port=7777)
    copynet.start()

    import time
    time.sleep(2)

    actor = tcp_actor("127.0.0.1", 7777, "inet")

    copynet.receive("message")
    
    data = actor.recv(128)

    assert data == "message"

    copynet.close()
