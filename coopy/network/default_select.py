import six
from select import select
import os
import socket
import zlib
import struct

if six.PY3:
    import pickle
    from queue import Queue
else:
    import cPickle as pickle
    from Queue import Queue
import threading
import logging
import sys


from coopy.network.network import prepare_data, CopyNetPacket, CopyNetClient,\
                                  CopyNetSnapshotThread

COPYNET_MASTER_PREFIX = '[coopynet - master]'
COPYNET_SLAVE_PREFIX = '[coopynet - slave]'

l = logging.getLogger("coopy")

_minfo = lambda x: l.info("%s %s" % (COPYNET_MASTER_PREFIX, x))
_sinfo = lambda x: l.info("%s %s" % (COPYNET_SLAVE_PREFIX, x))

_mdebug = lambda x: l.debug("%s %s" % (COPYNET_MASTER_PREFIX, x))
_sdebug = lambda x: l.debug("%s %s" % (COPYNET_SLAVE_PREFIX, x))

_mwarn = lambda x: l.warn("%s %s" % (COPYNET_MASTER_PREFIX, x))
_swarn = lambda x: l.warn("%s %s" % (COPYNET_SLAVE_PREFIX, x))

COPYNET_SOCK = '/tmp/coopy.sock'
COPYNET_HEADER = '!Ic'

_HEADER_SIZE = struct.calcsize(COPYNET_HEADER)

#TODO: re-write all code below!!! :) (and tests)

class CopyNet(threading.Thread):
    def __init__(self,
                 obj,
                 host=None,
                 port=5466,
                 max_clients=5,
                 password=b'copynet',
                 ipc=False):

        threading.Thread.__init__(self)
        self.obj = obj
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.password = password
        self.ipc = ipc

        self.clientmap = {}
        self.queues = {}

        if not self.ipc:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        if not host:
            host = socket.gethostbyname(socket.gethostname())

        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if not self.ipc:
            self.server.bind((host, port))
        else:
            self.server.bind(COPYNET_SOCK)

        self.server.listen(max_clients)
        _minfo("Listening to %d" % max_clients)

    def close(self):
        self.running = False
        try:
            self.server.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass
        self.server.close()
        if self.ipc:
            os.remove(COPYNET_SOCK)

    def receive(self, message):
        _mdebug('Receive')

        if len(self.clientmap) == 0:
            return

        (header, data) = prepare_data(message)
        self.broadcast(header, data)

    def broadcast(self, header, data):
       _mdebug('Broadcast')

       for copynetclient in self.clientmap.values():
            if copynetclient.state == 'r':
                copynetclient.client.sendall(header)
                copynetclient.client.sendall(data)
            elif copynetclient.state == 'b':
                self.queues[copynetclient.client].put_nowait(
                                                   CopyNetPacket(header,data))
            else:
                _mdebug('Unknow client state')

    def send_direct(self, client, message):
        (header, data) = prepare_data(message)
        client.sendall(header)
        client.sendall(data)

    def check_if_authorized_client(self, client):
        password = client.recv(20)

        if self.password != password.rstrip():
            unauthdata = struct.pack(COPYNET_HEADER, 0, b'n')
            client.sendall(unauthdata)
            client.close()
            _minfo('Client rejected')
            return False

        return True

    def initialize_client(self, client, address):
        self.clientmap[client] = CopyNetClient(client, address, 'r')
        self.queues[client] = Queue(999999)

    def disconnect(self, sock):
        _mdebug('Master received data. Close client')
        sock.close()
        del self.clientmap[sock]

    def run(self):
        self.running = True

        while self.running:

            try:
                to_read, to_write, exception_mode = \
                    select([self.server] + list(self.clientmap.keys()), [], [], 5)
            except socket.error as e:
                _mdebug("Select error")
                self.running = False
                break

            for sock in to_read:
                if sock == self.server:
                    try:
                        client, address = self.server.accept()
                    except Exception as e:
                        _mdebug('Cannot accept client: %s'  % e.message)
                        continue

                    _minfo('Server: got connection %d from %s' %
                                                   (client.fileno(), address))

                    if not self.check_if_authorized_client(client):
                       continue

                    _minfo('Client connected')
                    self.initialize_client(client, address)
                    #CopyNetSnapshotThread(self.clientmap[client], self.obj).start()
                else:
                    self.disconnect(sock)

            for sock in to_write:
                while not self.queues[sock].empty():
                    self.send_direct(sock, self.queues[sock].get_nowait())

        self.server.close()

class CopyNetSlave(threading.Thread):
    def __init__(self,
                 parent,
                 host='localhost',
                 port=5466,
                 password=b'copynet',
                 ipc=False):

        threading.Thread.__init__(self)
        self.parent = parent
        self.host = host
        self.port = port
        self.running = False
        self.lock = threading.RLock()

        try:
            if not ipc:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((host, self.port))
            else:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(COPYNET_SOCK)

            self.sock.sendall(password)
            _sdebug('Slave connected to server@%d' % self.port)
        except socket.error as e:
            _sdebug("Error connecting to server %s" % (e))
            raise Exception("Network Error: Could not connect to: %s:%d" %
                    (host, port))

    def acquire(self):
        self.lock.acquire(1)

    def release(self):
        self.lock.release()

    def close(self):
        self.running = False
        self.sock.close()

    def run(self):
        self.running = True

        while self.running:
            try:
                to_read, to_write, exception_mode = \
                    select([self.sock], [],[], 1)
            except Exception as e:
                _mdebug('Error on select %s..\nShutting down' % (e))
                self.running = False
                break

            _mdebug("waitin for data..")

            for sock in to_read:
                if sock == self.sock:
                    try:
                        data = self.sock.recv(_HEADER_SIZE)
                    except Exception as e:
                        _mdebug('Exception %s'  % e)
                        data = None

                    if not data:
                        _mdebug('Shutting down')
                        self.running = False
                        break
                    else:
                        try:
                            (psize, stype) = struct.unpack(COPYNET_HEADER, data)
                        except struct.error as e:
                            self.running = False
                            self.sock.close()
                            raise Exception("Unexpected error")
                        if stype == 'n':
                            self.sock.close()
                            raise Exception("Not authorized")

                        _sdebug('Reading %d bytes' % (psize))
                        buf = ''

                        while len(buf) < psize:
                            buf += self.sock.recv(4096)

                        un_data = zlib.decompress(buf)

                        self.lock.acquire(1)
                        if stype == 'a':
                            _sdebug('Receiving action')
                            action = picke.loads(str(un_data))
                            action.execute_action(self.parent.obj)
                            _sdebug(str(action))
                        else:
                            _sdebug('Receiving system')
                            self.parent.obj = pickle.loads(str(un_data))
                        self.lock.release()

                else:
                    _sdebug("Unexcpected")

        _mdebug("Slave close")
        self.sock.close()
