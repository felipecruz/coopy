import threading
import logging
import pickle
import os
import tempfile
from pickle import Pickler, Unpickler

from coopy import fileutils as fu

from os import path

logger = logging.getLogger("coopy")

class SnapshotManager(object):
    def __init__(self, basedir, durability="buffered"):
        self.durability = durability
        if len(basedir) > 0:
            basedir = basedir.replace('\\','/')
            if not basedir.endswith('/'):
                basedir += '/'
        else:
            basedir =  './'

        self.basedir = basedir

    def take_snapshot(self, object, before_publish=None):
        """Publish only a fully written, synced, and closed snapshot.

        The caller coordinates journals via before_publish while holding its
        domain lock. A failed publication must leave those journals intact.
        """
        destination = fu.next_snapshot_file(self.basedir)
        # The temporary name cannot be discovered as a checkpoint. Keep it on
        # the same filesystem so publication is a single atomic rename.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.basedir,
                                             prefix=".coopy-snapshot-",
                                             delete=False) as file:
                temporary = file.name
                Pickler(file, pickle.HIGHEST_PROTOCOL).dump(object)
                file.flush()
                os.fsync(file.fileno())
            if before_publish:
                before_publish(destination)
            os.replace(temporary, destination)
            temporary = None
            if self.durability == "sync":
                fu.sync_directory(self.basedir)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
                except OSError:
                    # Cleanup is best effort: preserve the snapshot failure
                    # for the caller. This hidden file cannot become a checkpoint.
                    logger.warning("Unable to remove incomplete snapshot %s",
                                   temporary, exc_info=True)

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
            try:
                self.proxy.take_snapshot()
            except Exception:
                logger.exception("Scheduled snapshot failed; retaining previous checkpoint")

    def stop(self):
        self.finished.set()
        if self is not threading.current_thread():
            self.join()
