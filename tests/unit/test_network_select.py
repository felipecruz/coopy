"""Socket framing, lifecycle, and explicit unsynchronized failure states."""
import socket
import struct
import time

import pytest

from coopy.base import CoopyProxy
from coopy.network.default_select import CopyNet, CopyNetSlave, _recv_exactly
from coopy.network.network import COPYNET_HEADER, prepare_data
from tests.domain import Wiki


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


def read_packet(sock):
    size, kind = struct.unpack(COPYNET_HEADER, _recv_exactly(sock, 5))
    return kind, _recv_exactly(sock, size)


def authenticate(sock, password=b'copynet'):
    sock.sendall(struct.pack('!I', len(password)) + password)


@pytest.fixture
def master():
    master = CopyNet('initial state', host='127.0.0.1', port=0)
    master.start()
    try:
        yield master
    finally:
        master.close()
        assert not master.is_alive()


def connect(master):
    sock = socket.create_connection(master.server.getsockname(), timeout=3)
    authenticate(sock)
    assert read_packet(sock)[0] == b's'
    assert read_packet(sock) == (b'r', b'')
    return sock


def test_broadcast_and_send_direct_follow_bootstrap(master):
    import pickle
    import zlib

    with connect(master) as first, connect(master) as second:
        master.receive(b'broadcast')
        for sock in (first, second):
            kind, data = read_packet(sock)
            assert kind == b's'
            assert pickle.loads(zlib.decompress(data)) == b'broadcast'
        with master.clients_lock:
            target = next(c for c in master.clientmap.values()
                          if c.address == first.getsockname())
        master.send_direct(target.client, b'direct')
        assert pickle.loads(zlib.decompress(read_packet(first)[1])) == b'direct'
        second.settimeout(0.05)
        with pytest.raises(socket.timeout):
            second.recv(1)


def test_master_disconnects_senders(master):
    with connect(master) as sock:
        sock.sendall(b'unexpected client data')
        wait_for(lambda: not master.clientmap)


def test_fragmented_authentication_does_not_block_other_clients(master):
    with socket.create_connection(master.server.getsockname(), timeout=3) as slow:
        packet = struct.pack('!I', 7) + b'copynet'
        slow.sendall(packet[:1])
        with connect(master):
            for byte in packet[1:]:
                slow.sendall(bytes([byte]))
            assert read_packet(slow)[0] == b's'
            assert read_packet(slow) == (b'r', b'')


@pytest.mark.parametrize('password', [b'wrong', b'', b'copynet-too-long'])
def test_rejected_slave_stays_unsynchronized(master, password):
    proxy = CoopyProxy(Wiki(), [])
    slave = CopyNetSlave(proxy, *master.server.getsockname(), password=password)
    proxy.slave = slave
    slave.start()
    try:
        slave.join(3)
        assert not slave.is_alive()
        assert not slave.synchronized
        assert 'authorized' in slave.error
        with pytest.raises(RuntimeError, match='not synchronized'):
            proxy.get_page('anything')
    finally:
        proxy.close()


@pytest.fixture
def fake_master():
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen()
    proxy = CoopyProxy(Wiki(), [])
    slave = CopyNetSlave(proxy, *server.getsockname())
    proxy.slave = slave
    peer, _ = server.accept()
    peer.settimeout(3)
    assert _recv_exactly(peer, 11) == struct.pack('!I', 7) + b'copynet'
    slave.start()
    try:
        yield proxy, slave, peer
    finally:
        slave.close()
        peer.close()
        server.close()
        assert not slave.is_alive()


def test_fragmented_snapshot_stays_private_until_ready(fake_master):
    proxy, slave, peer = fake_master
    original = proxy.obj
    snapshot = Wiki()
    snapshot.pages['bootstrap'] = 'value'
    header, payload = prepare_data(snapshot)
    for byte in header + payload:
        peer.sendall(bytes([byte]))
    assert not slave.synchronized
    assert proxy.obj is original
    with pytest.raises(RuntimeError, match='not synchronized'):
        proxy.pages
    for byte in struct.pack(COPYNET_HEADER, 0, b'r'):
        peer.sendall(bytes([byte]))
    assert slave.wait_until_synchronized(3)
    assert proxy.pages == {'bootstrap': 'value'}
    peer.close()
    slave.join(3)
    assert not slave.synchronized


@pytest.mark.parametrize('cut', ['header', 'payload', 'before-ready', 'ready-header',
                               'action-header', 'action-payload', 'corrupt', 'ready-first'])
def test_interrupted_or_invalid_bootstrap_is_not_exposed(fake_master, cut):
    from coopy.foundation import Action

    proxy, slave, peer = fake_master
    original = proxy.obj
    header, payload = prepare_data(Wiki())
    action_header, action_payload = prepare_data(Action(1, 'anything', None, (), {}))
    packets = {
        'header': header[:2],
        'payload': header + payload[:3],
        'before-ready': header + payload,
        'ready-header': header + payload + struct.pack(COPYNET_HEADER, 0, b'r')[:3],
        'action-header': header + payload + action_header[:2],
        'action-payload': header + payload + action_header + action_payload[:3],
        'corrupt': struct.pack(COPYNET_HEADER, 3, b's') + b'bad',
        'ready-first': struct.pack(COPYNET_HEADER, 0, b'r'),
    }
    peer.sendall(packets[cut])
    peer.shutdown(socket.SHUT_WR)
    slave.join(3)
    assert not slave.is_alive()
    assert not slave.synchronized
    assert slave.error
    assert proxy.obj is original


def test_close_interrupts_partial_packet_read(fake_master):
    _, slave, peer = fake_master
    peer.sendall(b'\x00')
    slave.close()
    assert not slave.is_alive()
    assert not slave.synchronized


@pytest.mark.parametrize('ready', [False, True])
def test_shutdown_keeps_slave_guard_and_rejects_promotion(fake_master, ready):
    proxy, slave, peer = fake_master
    if ready:
        header, payload = prepare_data(Wiki())
        peer.sendall(header + payload + struct.pack(COPYNET_HEADER, 0, b'r'))
        assert slave.wait_until_synchronized(3)
    proxy.shutdown()
    assert proxy.slave is slave
    assert not slave.synchronized
    with pytest.raises(RuntimeError, match='not synchronized'):
        proxy.get_page('anything')
    with pytest.raises(RuntimeError, match='unsynchronized'):
        proxy.take_snapshot()
    with pytest.raises(RuntimeError, match='slave'):
        proxy.start_primary(port=0)


def test_stop_at_ready_boundary_does_not_publish_snapshot(fake_master, monkeypatch):
    proxy, slave, peer = fake_master
    initial = proxy.obj
    receive = _recv_exactly

    def stop_before_ready(sock, size):
        packet = receive(sock, size)
        if packet == struct.pack(COPYNET_HEADER, 0, b'r'):
            slave.close()
        return packet

    monkeypatch.setattr('coopy.network.default_select._recv_exactly', stop_before_ready)
    header, payload = prepare_data(Wiki())
    peer.sendall(header + payload)
    # Complete the pending snapshot before sending the instrumented marker.
    peer.sendall(struct.pack(COPYNET_HEADER, 0, b'r'))
    slave.join(3)
    assert not slave.is_alive()
    assert not slave.synchronized
    assert proxy.obj is initial


def test_second_receiver_is_rejected(fake_master):
    proxy, slave, _ = fake_master
    with pytest.raises(RuntimeError, match='already'):
        proxy.start_replica('127.0.0.1', 0)
    assert proxy.slave is slave


def test_connection_failure_keeps_slave_unsynchronized(monkeypatch):
    def refuse(*args):
        raise ConnectionRefusedError('connection refused')

    monkeypatch.setattr(socket.socket, 'connect', refuse)
    proxy = CoopyProxy(Wiki(), [])
    try:
        with pytest.raises(ConnectionRefusedError):
            proxy.start_replica('127.0.0.1', 0)
        assert proxy.slave is not None
        assert not proxy.slave.synchronized
        assert 'refused' in proxy.slave.error
        with pytest.raises(RuntimeError, match='not synchronized'):
            proxy.get_page('anything')
    finally:
        proxy.close()


def test_failed_master_snapshot_does_not_synchronize_client(monkeypatch):
    master = CopyNet(Wiki(), host='127.0.0.1', port=0)
    master.start()
    proxy = CoopyProxy(Wiki(), [])
    original = proxy.obj
    monkeypatch.setattr('coopy.network.default_select.prepare_data',
                        lambda value: (_ for _ in ()).throw(ValueError('cannot serialize')))
    try:
        slave = proxy.start_replica(*master.server.getsockname())
        slave.join(3)
        assert not slave.is_alive()
        assert not slave.synchronized
        assert proxy.obj is original
        wait_for(lambda: not master.clientmap)
    finally:
        proxy.close()
        master.close()


def test_unix_socket_bootstrap_and_cleanup(monkeypatch):
    import os
    import tempfile

    # macOS limits Unix socket paths to 104 bytes; pytest's temp root is longer.
    with tempfile.TemporaryDirectory(prefix='coopy-', dir='/tmp') as directory:
        address = os.path.join(directory, 'replication.sock')
        monkeypatch.setattr('coopy.network.default_select.COPYNET_SOCK', address)
        master = CopyNet(Wiki(), ipc=True)
        master.start()
        proxy = CoopyProxy(Wiki(), [])
        try:
            slave = proxy.start_replica('unused', 0, ipc=True)
            assert slave.wait_until_synchronized(3)
            assert proxy.pages == {}
        finally:
            proxy.close()
            master.close()
        assert not os.path.exists(address)


def test_master_listens_on_loopback_without_hostname_lookup(monkeypatch):
    # resolving the own hostname blocked for ~30s on macOS CI runners
    def no_lookup(*args):
        raise AssertionError('hostname lookup attempted')
    monkeypatch.setattr(socket, 'gethostbyname', no_lookup)
    monkeypatch.setattr(socket, 'gethostname', no_lookup)

    proxy = CoopyProxy(Wiki(), [])
    proxy.start_primary(port=0)
    try:
        assert proxy.master.server.getsockname()[0] == '127.0.0.1'
    finally:
        proxy.shutdown()
        proxy.close()

    master = CopyNet(Wiki(), host=None, port=0)
    try:
        assert master.server.getsockname()[0] == '127.0.0.1'
    finally:
        master.close()
