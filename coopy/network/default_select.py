"""Ordered, trusted-peer replication with an explicit bootstrap boundary."""

import hmac
import logging
import os
import pickle
import socket
import struct
import threading
import time
import zlib
from collections import deque
from select import select

from coopy.foundation import RestoreClock
from coopy.network.network import COPYNET_HEADER, COPYNET_SOCK, prepare_data

logger = logging.getLogger("coopy")
_HEADER_SIZE = struct.calcsize(COPYNET_HEADER)
_AUTH_HEADER = struct.Struct("!I")
_MAX_PASSWORD = 4096


def _recv_exactly(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            break
        chunks.extend(chunk)
    return bytes(chunks)


class _Client:
    def __init__(self, client, address):
        self.client = client
        self.address = address
        self.state = "auth"
        self.auth = bytearray()
        self.deadline = time.monotonic() + 5
        self.queue = deque()
        self.offset = 0


DEFAULT_HOST = "127.0.0.1"


class CopyNet(threading.Thread):
    def __init__(
        self,
        obj,
        host=DEFAULT_HOST,
        port=5466,
        max_clients=5,
        password=b"copynet",
        ipc=False,
        lock=None,
    ):
        super().__init__(daemon=True)
        self.obj = obj
        self.lock = lock if lock is not None else threading.RLock()
        self.clients_lock = threading.RLock()
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.password = password
        self.ipc = ipc
        self.clientmap = {}
        self.queues = {}
        self.running = False
        self.stopped = threading.Event()
        self.server = socket.socket(socket.AF_UNIX if ipc else socket.AF_INET, socket.SOCK_STREAM)
        # Replication sends pickles, which can run code when loaded, so only
        # listen on loopback unless the caller asks for another interface.
        # No hostname lookup: it can block for ~30s on hosts that can't
        # resolve their own name.
        if not host:
            host = DEFAULT_HOST
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(COPYNET_SOCK if ipc else (host, port))
        self.server.listen(max_clients)
        self.server.setblocking(False)

    def close(self):
        self.stopped.set()
        self.running = False
        self.server.close()
        with self.clients_lock:
            for sock in list(self.clientmap):
                self.disconnect(sock)
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=2)
        if self.ipc and os.path.exists(COPYNET_SOCK):
            os.remove(COPYNET_SOCK)

    def receive_before(self, message):
        pass

    def receive_exception(self, message):
        pass

    def receive(self, message):
        # Proxy publication holds the same lock used by snapshot capture.
        with self.lock:
            self.broadcast(*prepare_data(message))

    def broadcast(self, header, data):
        with self.clients_lock:
            for client in self.clientmap.values():
                if client.state in ("b", "c", "r"):
                    client.queue.append((header + data, "action"))

    def send_direct(self, sock, message):
        header, data = prepare_data(message)
        with self.clients_lock:
            self.clientmap[sock].queue.append((header + data, "action"))

    def initialize_client(self, sock, address):
        sock.setblocking(False)
        with self.clients_lock:
            client = _Client(sock, address)
            self.clientmap[sock] = client
            self.queues[sock] = client.queue

    def disconnect(self, sock):
        with self.clients_lock:
            sock.close()
            self.clientmap.pop(sock, None)
            self.queues.pop(sock, None)

    def _authenticate(self, client):
        chunk = client.client.recv(4096)
        if not chunk:
            self.disconnect(client.client)
            return
        client.auth.extend(chunk)
        if len(client.auth) < _AUTH_HEADER.size:
            return
        size = _AUTH_HEADER.unpack(client.auth[: _AUTH_HEADER.size])[0]
        if size > _MAX_PASSWORD:
            self.disconnect(client.client)
            return
        if len(client.auth) < _AUTH_HEADER.size + size:
            return
        password = bytes(client.auth[_AUTH_HEADER.size :])
        # This timing-safe comparison does not encrypt the plaintext handshake.
        if not hmac.compare_digest(password, self.password):
            client.queue.append((struct.pack(COPYNET_HEADER, 0, b"n"), "reject"))
            client.state = "reject"
            return
        # Capture and registration share the mutation/publication lock. No
        # action can fall between the snapshot and this client's action queue.
        with self.lock:
            header, data = prepare_data(self.obj)
            with self.clients_lock:
                client.queue.append((header + data, "snapshot"))
                client.state = "b"

    def _write_client(self, client):
        # Only this event loop writes sockets; packets cannot interleave.
        with self.clients_lock:
            if not client.queue:
                return
            packet, kind = client.queue[0]
            sent = client.client.send(memoryview(packet)[client.offset :])
            if not sent:
                raise ConnectionError("peer stopped receiving")
            client.offset += sent
            if client.offset != len(packet):
                return
            client.queue.popleft()
            client.offset = 0
            if kind == "snapshot":
                # Include every action queued during snapshot transfer before
                # exposing readiness. Later live actions follow this marker.
                client.queue.append((struct.pack(COPYNET_HEADER, 0, b"r"), "ready"))
                client.state = "c"
            elif kind == "ready":
                client.state = "r"
            elif kind == "reject":
                self.disconnect(client.client)

    def run(self):
        self.running = not self.stopped.is_set()
        try:
            while not self.stopped.is_set():
                with self.clients_lock:
                    clients = list(self.clientmap.values())
                    writable = [c.client for c in clients if c.queue]
                try:
                    readable, writable, _ = select(
                        [self.server] + [c.client for c in clients], writable, [], 0.05
                    )
                except (OSError, ValueError):
                    break
                for sock in readable:
                    if sock is self.server:
                        try:
                            client, address = self.server.accept()
                            if len(self.clientmap) >= self.max_clients:
                                client.close()
                            else:
                                self.initialize_client(client, address)
                        except OSError:
                            pass
                    else:
                        client = self.clientmap.get(sock)
                        if client is None:
                            continue
                        try:
                            if client.state == "auth":
                                self._authenticate(client)
                            else:
                                self.disconnect(sock)
                        except BlockingIOError:
                            pass
                        except Exception:
                            logger.exception("Replication bootstrap failed")
                            self.disconnect(sock)
                for sock in writable:
                    client = self.clientmap.get(sock)
                    if client is not None:
                        try:
                            self._write_client(client)
                        except BlockingIOError:
                            pass
                        except OSError:
                            self.disconnect(sock)
                for client in clients:
                    if client.state == "auth" and time.monotonic() > client.deadline:
                        self.disconnect(client.client)
        finally:
            self.running = False
            self.server.close()
            with self.clients_lock:
                for sock in list(self.clientmap):
                    self.disconnect(sock)


class CopyNetSlave(threading.Thread):
    def __init__(
        self, parent, host="localhost", port=5466, password=b"copynet", ipc=False, *, connect=True
    ):
        super().__init__(daemon=True)
        self.parent = parent
        self.host = host
        self.port = port
        self.lock = getattr(parent, "lock", threading.RLock())
        self.running = False
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.error = None
        self.address = COPYNET_SOCK if ipc else (host, port)
        self.password = password
        self.sock = socket.socket(socket.AF_UNIX if ipc else socket.AF_INET, socket.SOCK_STREAM)
        if connect:
            self._connect()

    def _connect(self):
        try:
            self.sock.connect(self.address)
            self.sock.sendall(_AUTH_HEADER.pack(len(self.password)) + self.password)
        except Exception as exc:
            self.error = str(exc)
            self.stopped.set()
            self.sock.close()
            raise

    @property
    def synchronized(self):
        return self.ready.is_set()

    def wait_until_synchronized(self, timeout=None):
        return self.ready.wait(timeout) and self.synchronized

    def acquire(self):
        self.lock.acquire()

    def release(self):
        self.lock.release()

    def close(self):
        with self.lock:
            self.stopped.set()
            self.ready.clear()
            self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        if self.is_alive() and self is not threading.current_thread():
            self.join(timeout=2)

    def run(self):
        self.running = not self.stopped.is_set()
        pending = None
        try:
            while not self.stopped.is_set():
                header = _recv_exactly(self.sock, _HEADER_SIZE)
                if len(header) != _HEADER_SIZE:
                    raise ConnectionError("Master disconnected before a complete header")
                size, kind = struct.unpack(COPYNET_HEADER, header)
                if kind == b"n":
                    raise PermissionError("Not authorized by master")
                if kind == b"r":
                    if size or pending is None or self.synchronized:
                        raise ValueError("Unexpected synchronization marker")
                    with self.lock:
                        if self.stopped.is_set():
                            break
                        self.parent.obj = pending
                        pending = None
                        self.ready.set()
                    continue
                if kind not in (b"s", b"a"):
                    raise ValueError("Unknown replication packet")
                payload = _recv_exactly(self.sock, size)
                if len(payload) != size:
                    raise ConnectionError("Master disconnected mid-message")
                value = pickle.loads(zlib.decompress(payload))
                with self.lock:
                    if self.stopped.is_set():
                        break
                    if kind == b"s":
                        if pending is not None or self.synchronized:
                            raise ValueError("Unexpected snapshot")
                        pending = value
                    else:
                        obj = self.parent.obj if self.synchronized else pending
                        if obj is None:
                            raise ValueError("Action received before snapshot")
                        clock = RestoreClock.for_action(value)
                        obj._clock = clock
                        try:
                            value.execute_action(obj)
                        except Exception:
                            clock.check_calls()
                            if not getattr(value, "raised", False):
                                self.ready.clear()
                                raise
                        else:
                            clock.check_calls()
                            if getattr(value, "raised", False):
                                self.ready.clear()
                                raise ValueError("Action outcome differs from master")
                        clock.check_complete()
        except Exception as exc:
            if not self.stopped.is_set():
                self.error = str(exc)
                logger.warning("Slave unsynchronized: %s", exc)
        finally:
            self.ready.clear()
            self.running = False
            self.sock.close()
