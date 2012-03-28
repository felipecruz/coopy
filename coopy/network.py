import os
import socket
import select
import zlib
import struct
import cPickle
import threading
import logging
import sys

import foundation
from foundation import Action

from Queue import Queue

COPYNET_MASTER_PREFIX = '[coopynet - master]'
COPYNET_SLAVE_PREFIX = '[coopynet - slave]'
COPYNET_SOCK = '/tmp/coopy.sock'
COPYNET_HEADER = '!Ic'

l = logging.getLogger("coopy")

def prepare_data(data, stype='s'):
    if (isinstance(data, Action) or isinstance(data, foundation.Action)):
        stype = 's'
    
    data = cPickle.dumps(data)
    compressed_data = zlib.compress(data)
    value = len(compressed_data)
    header = struct.pack(COPYNET_HEADER, value, stype)
   
    return (header, compressed_data)

class CopyNetClient():
    def __init__(self, client, address, state):
        self.client = client
        self.address = address
        self.state = state
        
class CopyNetPacket():
    def __init__(self, header, data):
        self.header = header
        self.data = data
        
class CopyNetSnapshotThread(threading.Thread):
    def __init__(self, net_client, obj):
            threading.Thread.__init__ (self)
            self.net_client = net_client
            self.obj = obj
    def run(self):
        (header,data) = prepare_data(self.obj)
        self.net_client.client.sendall(header)
        self.net_client.client.sendall(data)
        self.net_client.state = 'r'

#TODO: re-write all code below!!! :) (and tests)

class CopyNet(threading.Thread):
    def __init__(self, 
                 obj, 
                 port=5466, 
                 max_clients=5, 
                 password='copynet', 
                 ipc=False
        ):
        
        threading.Thread.__init__ (self)
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
        
        host = socket.gethostbyname(socket.gethostname())
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if not self.ipc:
            self.server.bind((host,port))
        else:
            self.server.bind(COPYNET_SOCK)
        
        l.info(COPYNET_MASTER_PREFIX + "Listening to %d" % max_clients)
        self.server.listen(max_clients)
        
    def close(self):
        self.running = False
        self.server.close()
        if self.ipc:
            os.remove(COPYNET_SOCK)
        
    def receive(self, message):
        if not self.outputs:
            return
        (header,data) = prepare_data(message)
        self.broadcast(header, data)
        
    def broadcast(self, header, data):
       for copynetclient in self.clientmap.values():
            if copynetclient.state == 'r':
                copynetclient.client.sendall(header)
                copynetclient.client.sendall(data)
            elif copynetclient.state == 'b':
                self.queues[copynetclient.client].put_nowait(CopyNetPacket(header,data))
            else:
                l.debug(COPYNET_MASTER_PREFIX + 'Unknow client state')
                
    def send_direct(self, client, message):
        (header,data) = prepare_data(message)
        client.sendall(header)
        client.sendall(data)
                   
    def run(self):
        inputs = [self.server]
        self.outputs = []
        self.running = True
        while self.running and self.server.fileno() > 0:

            try:
                inr,our,exr = select.select(inputs, [], [], 5)
            except select.error, e:
                break

            for s in inr:
                if s == self.server:
                    try:
                        client, address = self.server.accept()
                    except Exception as e:
                        l.debug(COPYNET_MASTER_PREFIX + 'server closed, shuting down')
                        l.debug(e)
                        sys.exit(0)

                    l.info(COPYNET_MASTER_PREFIX + 'Server: got connection %d from %s' % (client.fileno(), address))   
                    
                    password = client.recv(20)
                    if self.password != password.rstrip():
                        unauthdata = header = struct.pack(COPYNET_HEADER, 0, 'n')
                        client.sendall(unauthdata)
                        client.close()
                        break
                    
                     
                    self.clients += 1
                    inputs.append(client)
                    self.outputs.append(client)
                    self.clientmap[client] = CopyNetClient(client, address, 'b')
                    self.queues[client] = Queue(999999)
                    CopyNetSnapshotThread(self.clientmap[client], self.obj).start()

                else:
                    try:
                        data = s.recv(1024)
                        if data:
                            l.info(COPYNET_MASTER_PREFIX + "receivd" + str(data))
                        else:
                            self.clients -= 1
                            s.close()
                            inputs.remove(s)
                            self.outputs.remove(s)
                            del self.clientmap[s]
                                
                    except socket.error, e:
                        inputs.remove(s)
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
            l.debug(COPYNET_SLAVE_PREFIX + 'Slave connected to server@%d' % self.port)
        except socket.error, e:
            l.debug(COPYNET_SLAVE_PREFIX + "Error connecting to server %s" % (e))
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
                inr, our, exr = select.select([self.sock], [],[], 5)
            except Exception as e:
                l.debug(COPYNET_SLAVE_PREFIX + 'Error on select %s..\nShutting donw' % (e))
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
                        l.info(COPYNET_SLAVE_PREFIX + 'Shutting down')
                        self.flag = True
                        break
                    else:
                        try:
                            (psize,stype) = struct.unpack(COPYNET_HEADER, data)
                        except struct.error, e:
                            return ''
                        if stype == 'n':
                            raise Exception("Not authorized")
                            
                        l.debug(COPYNET_SLAVE_PREFIX + 'Reading %d bytes' % (size))                  
                        buf = ''
                        
                        while len(buf) < psize:
                            buf += self.sock.recv(4096)
                                              
                        un_data = zlib.decompress(buf)
                        
                        self.lock.acquire(1)
                        if stype == 'a':
                            l.debug(COPYNET_SLAVE_PREFIX + 'Receiving action')
                            action = cPickle.loads(str(un_data))
                            action.execute_action(self.parent.obj)
                            l.debug(COPYNET_SLAVE_PREFIX + str(action))
                        else:
                            l.debug(COPYNET_SLAVE_PREFIX + 'Receiving system')
                            self.obj = cPickle.loads(str(un_data))
                            self.parent.obj = self.obj
                        self.lock.release()

                else:
                    l.debug(COPYNET_SLAVE_PREFIX + "Unexcpected")
        self.sock.close()
