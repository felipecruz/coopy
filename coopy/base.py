'''
Created on Dec 6, 2011

@author: felipe j. cruz
'''
__author__ = "Felipe Cruz <felipecruz@loogica.net>"
__license__ = "BSD"
__version__ = "0.5a"

import six
import os
import logging
import threading
import types

if six.PY3:
    import _thread as thread
else:
    import thread

from logging.handlers import RotatingFileHandler
from datetime import datetime

from coopy import fileutils
from coopy.foundation import Action, RecordClock, Publisher
from coopy.journal import DiskJournal
from coopy.restore import restore
from coopy.snapshot import SnapshotManager, SnapshotTimer
from coopy.utils import method_or_none, action_check, inject

from coopy.network.default_select import CopyNet, CopyNetSlave

CORE_LOG_PREFIX = '[CORE] '

def logging_config(basedir="./"):
    log_file_path = os.path.join(basedir, "coopy.log")
    result = logging.getLogger("coopy")
    result.setLevel(logging.DEBUG)

    handler = RotatingFileHandler(log_file_path, "a", 1000000, 10)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s ' \
                                 '- %(message)s', '%a, %d %b %Y %H:%M:%S')
    handler.setFormatter(formatter)
    result.addHandler(handler)

logging_config()
logger = logging.getLogger("coopy")


def init_persistent_system(obj, basedir=None):
    # a system object is needed in order to coopy work
    if not obj:
        raise Exception(CORE_LOG_PREFIX +
                "Must input a valid object if there's no snapshot files")

    # if obj is a class, change obj to an insance
    if isinstance(obj, type):
        obj = obj()

    # first step is to check basedir argument. if isn't defined
    # coopy will create a directory name based on system class
    if not basedir:
        basedir = fileutils.obj_to_dir_name(obj)

    # convert some string to a valid directory name
    basedir = fileutils.name_to_dir(basedir)

    # get looger

    # check if basedir exists, if not, create it
    try:
        os.listdir(basedir)
    except os.error:
        os.mkdir(basedir)

    # if no snapshot files, create first one with a 'empty' system
    if not fileutils.last_snapshot_file(basedir):
        logger.info(CORE_LOG_PREFIX + "No snapshot files..")
        SnapshotManager(basedir).take_snapshot(obj)

    # measure restore time
    start = datetime.utcnow()
    logger.info(CORE_LOG_PREFIX + "coopy init....")

    # inject clock on system object
    inject(obj, '_clock', RecordClock())

    # RestoreHelper will recover a system state based on snapshots and
    # transations files extracting actions executed previously and
    # re-executing them again
    obj = restore(obj, basedir)

    end = datetime.utcnow()
    delta = end - start
    logger.info(CORE_LOG_PREFIX + "spent " + str(delta) + "microseconds")

    journal = DiskJournal(basedir)
    journal.setup()

    snapshot_manager = SnapshotManager(basedir)

    return CoopyProxy(obj, [journal], snapshot_manager=snapshot_manager)

def init_system(obj, subscribers):
    # return a coopy proxy instead of a system instance
    proxy = CoopyProxy(obj, subscribers)
    return proxy

class CoopyProxy():
    def __init__(self, obj, subscribers, snapshot_manager=None):
        self.obj = obj
        self.publisher = Publisher(subscribers)
        self.lock = threading.RLock()
        self.master = None
        self.slave = None
        self.snapshot_manager = snapshot_manager
        self.snapshot_timer = None

    def start_snapshot_manager(self, snapshot_time):
        import time
        self.snapshot_timer = SnapshotTimer(snapshot_time, self)
        time.sleep(snapshot_time)
        self.snapshot_timer.start()

    def start_master(self, port=8012, password=None, ipc=False):
        self.server = CopyNet(self.obj,
                              port=port,
                              password=password,
                              ipc=ipc)
        self.server.start()
        self.publisher.register(self.server)
        self.slave = None

    def start_slave(self, host, port, password=None, ipc=None):
        self.server = None
        self.slave = CopyNetSlave(self.obj,
                                    self,
                                    host=host,
                                    password=password,
                                    port=port,
                                    ipc=ipc)
        self.slave.start()

    def __getattr__(self, name):
        method =  method_or_none(self.obj, name)

        if not method:
            return getattr(self.obj, name)

        (readonly,unlocked,abort_exception) = action_check(method)

        #TODO: re-write
        if not readonly and hasattr(self, 'slave') and self.slave:
            raise Exception('This is a slave/read-only instance.')

        def method(*args, **kwargs):
            try:
                if not unlocked:
                    self.lock.acquire(1)

                #record all calls to clock.now()
                self.obj._clock = RecordClock()

                if six.PY3:
                    thread_ident = thread.get_ident()
                else:
                    thread_ident = thread.get_ident()
                action = Action(thread_ident,
                                name,
                                datetime.now(),
                                args,
                                kwargs)
                system = None

                if not readonly:
                    self.publisher.publish_before(action)

                try:
                    system = action.execute_action(self.obj)
                except Exception as e:
                    logger.debug(CORE_LOG_PREFIX + 'Error: ' + str(e))
                    if abort_exception:
                        logger.debug(CORE_LOG_PREFIX +
                                'Aborting action' + str(action))
                    if not abort_exception:
                        self.publisher.publish_exception(action)
                    raise e

                #restore clock
                action.timestamps = self._clock.timestamps

                if not readonly:
                    self.publisher.publish(action)

            finally:
                if not unlocked:
                    self.lock.release()

            return system
        return method

    def take_snapshot(self):
        if self.slave:
            self.slave.acquire()
        if self.snapshot_manager:
            self.snapshot_manager.take_snapshot(self.obj)
        if self.slave:
            self.slave.release()

    def close(self):
        self.publisher.close()
        logging.shutdown()
        if self.snapshot_timer:
            self.snapshot_timer.stop()

    def shutdown(self):
        if self.master:
            self.server.close()
        if self.slave:
            self.slave.close()
