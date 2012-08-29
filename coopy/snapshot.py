import six
import threading
import logging
import pickle
from coopy import fileutils as fu

from os import path

if six.PY3:
    from pickle import Pickler, Unpickler
else:
    from cPickle import Pickler, Unpickler

logger = logging.getLogger("coopy")

class SnapshotManager(object):
    def __init__(self, basedir):
        if len(basedir) > 0:
            basedir = basedir.replace('\\','/')
            if not basedir.endswith('/'):
                basedir += '/'
        else:
            basedir =  './'

        self.basedir = basedir

    def take_snapshot(self, object):
        file = open(fu.next_snapshot_file(self.basedir), "wb")
        logger.debug("Taking snapshot on: " + file.name)
        pickler = Pickler(file, pickle.HIGHEST_PROTOCOL)
        pickler.dump(object)
        file.flush()
        file.close()

    def recover_snapshot(self):
        file = open(path.join(self.basedir,fu.last_snapshot_file(self.basedir)),"rb")
        if not file:
            return None
        logger.debug("Recovering snapshot from: " + file.name)
        unpickler = Unpickler(file)
        return unpickler.load()


class SnapshotTimer(threading.Thread):
    def __init__(self, snapshot_time, proxy):
        threading.Thread.__init__ (self)
        self.snapshot_time = snapshot_time
        self.proxy = proxy
        self.finished = threading.Event()

    def run(self):
        while not self.finished.isSet():
            self.proxy.take_snapshot()
            self.finished.wait(self.snapshot_time)

    def stop(self):
        self.finished.set()
        self.join()
