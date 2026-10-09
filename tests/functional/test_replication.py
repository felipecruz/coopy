import threading
from datetime import datetime

import pytest

from coopy.base import CoopyProxy, init_persistent_system
from coopy.decorators import readonly
from coopy.foundation import Action
from coopy.network.network import COPYNET_HEADER, prepare_data
from tests.unit.test_network_select import wait_for, fake_master


class Timeline:
    def __init__(self):
        self.events = []

    def add(self, number):
        self.events.append((number, self._clock.now(), self._clock.utcnow(),
                            self._clock.today()))

    def fail(self):
        raise ValueError('expected domain failure')

    @readonly
    def read(self):
        return list(self.events)


def test_populated_master_concurrent_catchup_clock_and_live_replay(monkeypatch, tmp_path):
    master = init_persistent_system(Timeline(), basedir=str(tmp_path / 'master'))
    replica = CoopyProxy(Timeline(), [])
    cached_write = replica.add
    for i in range(10):
        master.add(i)
    master.start_master(port=0, password='fragment-safe password longer than 20 bytes')
    host, port = master.master.server.getsockname()
    transfer_started = threading.Event()
    continue_transfer = threading.Event()
    original_write = master.master._write_client

    def pause_during_transfer(client):
        if client.queue[0][1] == 'snapshot' and not transfer_started.is_set():
            # Send a prefix of a real packet, then pause the transfer while
            # application writes continue and queue behind the snapshot.
            packet, _ = client.queue[0]
            client.offset += client.client.send(packet[:10])
            transfer_started.set()
            assert continue_transfer.wait(3)
        original_write(client)

    monkeypatch.setattr(master.master, '_write_client', pause_during_transfer)
    try:
        slave = replica.start_slave(host, port,
                                   password='fragment-safe password longer than 20 bytes')
        assert transfer_started.wait(3)
        assert not slave.synchronized
        with pytest.raises(RuntimeError, match='not synchronized'):
            replica.read()
        with pytest.raises(RuntimeError, match='unsynchronized'):
            replica.take_snapshot()
        writer = threading.Thread(target=lambda: [master.add(i) for i in range(10, 60)])
        writer.start()
        writer.join(3)
        assert not writer.is_alive(), 'network transfer blocked master writes'
        assert len(master.read()) == 60
        continue_transfer.set()
        assert slave.wait_until_synchronized(3)
        assert replica.read() == master.read()
        assert [event[0] for event in replica.read()] == list(range(60))
        with pytest.raises(Exception, match='read-only'):
            replica.add(60)
        with pytest.raises(RuntimeError, match='read-only'):
            cached_write(60)
        for i in range(60, 70):
            master.add(i)
        with pytest.raises(ValueError, match='expected domain failure'):
            master.fail()
        wait_for(lambda: replica.read() == master.read())
        assert slave.synchronized
        assert [event[0] for event in replica.read()] == list(range(70))
        master.shutdown()
        slave.join(3)
        assert not slave.synchronized
        with pytest.raises(RuntimeError, match='not synchronized'):
            replica.read()
    finally:
        continue_transfer.set()
        replica.close()
        master.shutdown()
        master.close()


def test_explicit_reconnect_replaces_stale_state_with_fresh_bootstrap():
    master = CoopyProxy(Timeline(), [])
    replica = CoopyProxy(Timeline(), [])
    master.add(0)
    master.start_master(port=0)
    address = master.master.server.getsockname()
    try:
        first = replica.start_slave(*address)
        assert first.wait_until_synchronized(3)
        cached_read = replica.read
        with pytest.raises(RuntimeError, match='already'):
            replica.start_slave(*address)
        with pytest.raises(RuntimeError, match='active master'):
            master.start_slave(*address)
        with pytest.raises(RuntimeError, match='already'):
            master.start_master(port=0)
        replica.shutdown()
        with pytest.raises(RuntimeError, match='not synchronized'):
            cached_read()
        master.add(1)
        second = replica.start_slave(*address)
        assert second is not first
        assert second.wait_until_synchronized(3)
        assert not first.synchronized
        assert cached_read() == master.read()
        assert [event[0] for event in replica.read()] == [0, 1]
    finally:
        replica.close()
        master.close()


@pytest.mark.parametrize('raised', [False, True])
def test_replay_divergence_never_marks_slave_ready(fake_master, raised):
    import struct

    proxy, slave, peer = fake_master
    initial = proxy.obj
    snapshot = Timeline()
    action = Action(1, 'add' if raised else 'fail', datetime(2020, 1, 1),
                    (1,) if raised else (), {})
    action.results = [datetime(2020, 1, 1)] * 3
    action.raised = raised
    for value in (snapshot, action):
        header, payload = prepare_data(value)
        peer.sendall(header + payload)
    peer.sendall(struct.pack(COPYNET_HEADER, 0, b'r'))
    slave.join(3)
    assert not slave.is_alive()
    assert not slave.synchronized
    assert slave.error
    assert proxy.obj is initial
