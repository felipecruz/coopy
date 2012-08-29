import six
import zlib
import struct

if six.PY3:
    import pickle
else:
    import cPickle as pickle

import threading
import logging

from coopy import foundation
from coopy.foundation import Action

COPYNET_MASTER_PREFIX = '[coopynet - master]'
COPYNET_SLAVE_PREFIX = '[coopynet - slave]'
COPYNET_SOCK = '/tmp/coopy.sock'
COPYNET_HEADER = '!Ic'

l = logging.getLogger("coopy")

def prepare_data(data, stype=b's'):
    if (isinstance(data, Action) or isinstance(data, foundation.Action)):
        stype = b'a'

    data = pickle.dumps(data)
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
