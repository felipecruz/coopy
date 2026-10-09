import threading
import logging
import pickle
from pickle import Pickler, Unpickler

from coopy import fileutils as fu

from os import path

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
        with open(fu.next_snapshot_file(self.basedir), "wb") as file:
            logger.debug("Taking snapshot on: " + file.name)
            pickler = Pickler(file, pickle.HIGHEST_PROTOCOL)
            pickler.dump(object)

    def recover_snapshot(self):
        last_snapshot = fu.last_snapshot_file(self.basedir)
        if not last_snapshot:
            return None
        with open(path.join(self.basedir, last_snapshot), "rb") as file:
            logger.debug("Recovering snapshot from: " + file.name)
            return Unpickler(file).load()


class SnapshotTimer(threading.Thread):
    def __init__(self, snapshot_time, proxy):
        threading.Thread.__init__(self, daemon=True)
        self.snapshot_time = snapshot_time
        self.proxy = proxy
        self.finished = threading.Event()

    def run(self):
        # wait first: the first snapshot happens after snapshot_time
        while not self.finished.wait(self.snapshot_time):
            self.proxy.take_snapshot()

    def stop(self):
        self.finished.set()
        if self is not threading.current_thread():
            self.join()
