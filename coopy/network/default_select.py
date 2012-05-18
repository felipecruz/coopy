from select import select
import os
import socket
import zlib
import struct
import cPickle
import threading
import logging
import sys

from Queue import Queue

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

#TODO: re-write all code below!!! :) (and tests)

class CopyNet(threading.Thread):
    def __init__(self, 
                 obj, 
                 host=None,
                 port=3333, 
                 max_clients=5, 
                 password='copynet', 
                 ipc=False):
        
        threading.Thread.__init__(self)
        self.port = port
        self.max_clients = max_clients
        self.clients = 0
        self.clientmap = {}
        self.outputs = []
        self.queues = {}
        self.obj = obj
        self.password = password
        self.ipc = ipc
        
        if not self.ipc:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        
        if not host:
            host = socket.gethostbyname(socket.gethostname())
    
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if not self.ipc:
            self.server.bind((host,port))
        else:
            self.server.bind(COPYNET_SOCK)
       
        self.server.listen(max_clients)
        _minfo("Listening to %d" % max_clients)
 
    def close(self):
        self.running = False
        self.server.close()
        if self.ipc:
            os.remove(COPYNET_SOCK)
        
    def receive(self, message):
        _mdebug('Receive')
        if not self.outputs:
            return
        (header,data) = prepare_data(message)
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
        (header,data) = prepare_data(message)
        client.sendall(header)
        client.sendall(data)
                   
    def run(self):
        self.outputs = []
        self.running = True
        while self.running and self.server.fileno() > 0:
            try:
                inr, our, exr = select([self.server] + self.outputs, 
                                                                    [], [], 5)
            except socket.error, e:
                _mdebug("Select error")

            for s in inr:
                if s == self.server:
                    try:
                        client, address = self.server.accept()
                    except Exception as e:
                        _mdebug('Server closed, shuting down')
                        _mdebug(e.message)
                        sys.exit(0)

                    _minfo('Server: got connection %d from %s' % 
                                                   (client.fileno(), address))   
                    
                    password = client.recv(20)
                    if self.password != password.rstrip():
                        unauthdata = struct.pack(COPYNET_HEADER, 0, 'n')
                        client.sendall(unauthdata)
                        client.close()
                        break

                    _minfo('Client connected')
                     
                    self.clients += 1
                    self.outputs.append(client)
                    self.clientmap[client] = \
                                    CopyNetClient(client, address, 'r')
                    self.queues[client] = Queue(999999)
                    #CopyNetSnapshotThread(self.clientmap[client], self.obj).start()

                else:
                    _mdebug('Master received data. Close client')
                    s.recv(1024)
                    s.close()
                    self.clients -= 1
                    self.outputs.remove(s)
                    del self.clientmap[s]

            for s in our:
                while not self.queues[s].empty():
                    self.send_direct(s, self.queues[s].get_nowait())
                            
        self.server.close()

class CopyNetSlave(threading.Thread):
    def __init__(self, obj, parent, host='localhost', port=5466, password='copynet', ipc=False):
        threading.Thread.__init__ (self)
        self.flag = False
        self.port = int(port)
        self.host = host
        self.obj = obj
        self.parent = parent
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
        except socket.error, e:
            _sdebug("Error connecting to server %s" % (e))
            raise Exception("Network Error: Could not connect to: %s:%d" %(host, port))

    def acquire(self):
        self.lock.acquire(1)
    
    def release(self):
        self.lock.release()
        
    def close(self):
        self.flag = True
        self.sock.close()

    def run(self):
        while not self.flag and self.sock.fileno() > 0: 
            try:
                inr, our, exr = select([self.sock], [],[], 5)
            except Exception as e:
                _mdebug('Error on select %s..\nShutting down' % (e))
                sys.exit(-1)
            
            for i in inr:
                if i == self.sock:
                    size = struct.calcsize(COPYNET_HEADER)
                    try:
                        data = self.sock.recv(size)
                    except Exception as e:
                        l.debug(e)
                        data = None

                    if not data:
                        _sinfo('Shutting down')
                        self.flag = True
                        break
                    else:
                        try:
                            (psize,stype) = struct.unpack(COPYNET_HEADER, data)
                        except struct.error, e:
                            return ''
                        if stype == 'n':
                            raise Exception("Not authorized")
                            
                        _sdebug('Reading %d bytes' % (size))                  
                        buf = ''
                        
                        while len(buf) < psize:
                            buf += self.sock.recv(4096)
                                              
                        un_data = zlib.decompress(buf)
                        
                        self.lock.acquire(1)
                        if stype == 'a':
                            _sdebug('Receiving action')
                            action = cPickle.loads(str(un_data))
                            action.execute_action(self.parent.obj)
                            _sdebug(str(action))
                        else:
                            _sdebug('Receiving system')
                            self.obj = cPickle.loads(str(un_data))
                            self.parent.obj = self.obj
                        self.lock.release()

                else:
                    _sdebug("Unexcpected")
        self.sock.close()
