'''
Created on Dec 6, 2011

@author: felipe j. cruz
'''
__author__ = "Felipe Cruz <felipecruz@gmail.com>"
__license__ = "BSD"

import os
import time
import logging
import threading

from logging.handlers import RotatingFileHandler
from datetime import datetime

from coopy import __version__, fileutils
from coopy.foundation import Action, RecordClock, Publisher
from coopy.journal import DiskJournal
from coopy.integrity import Integrity, IDENTITY_FILE, validate_secret
from coopy.restore import recover
from coopy.snapshot import SnapshotManager, SnapshotTimer
from coopy.utils import method_or_none, action_check, inject
from coopy.validation import validate_system

from coopy.network.default_select import CopyNet, CopyNetSlave

CORE_LOG_PREFIX = '[CORE] '
DEFAULT_PASSWORD = b'copynet'

logger = logging.getLogger("coopy")
logger.addHandler(logging.NullHandler())

def logging_config(basedir="./"):
    log_file_path = os.path.abspath(os.path.join(basedir, "coopy.log"))
    result = logging.getLogger("coopy")
    result.setLevel(logging.DEBUG)

    # avoid duplicated log lines when called more than once
    for handler in result.handlers:
        if getattr(handler, 'baseFilename', None) == log_file_path:
            return

    handler = RotatingFileHandler(log_file_path, "a", 1000000, 10)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s ' \
                                 '- %(message)s', '%a, %d %b %Y %H:%M:%S')
    handler.setFormatter(formatter)
    result.addHandler(handler)

def _to_password(password):
    if password is None:
        return DEFAULT_PASSWORD
    if isinstance(password, str):
        return password.encode('utf-8')
    return password


def init_persistent_system(obj, basedir=None, *, recovery="strict",
                           durability="buffered", secret=None):
    validate_secret(secret)
    if recovery not in ("strict", "salvage"):
        raise ValueError("recovery must be 'strict' or 'salvage'")
    if durability not in ("buffered", "sync"):
        raise ValueError("durability must be 'buffered' or 'sync'")
    logging_config()

    # a system object is needed in order to coopy work
    if not obj:
        raise Exception(CORE_LOG_PREFIX +
                "Must input a valid object if there's no snapshot files")

    # if obj is a class, change obj to an insance
    if isinstance(obj, type):
        obj = obj()

    validate_system(obj)

    # first step is to check basedir argument. if isn't defined
    # coopy will create a directory name based on system class
    if not basedir:
        basedir = fileutils.obj_to_dir_name(obj)

    # convert some string to a valid directory name
    basedir = fileutils.name_to_dir(basedir)

    system_data_path = os.getcwd()

    # Salvage inspects existing storage without creating checkpoints/journals.
    if recovery == "salvage":
        inject(obj, '_clock', RecordClock())
        return recover(obj, basedir, mode="salvage", secret=secret)

    # check if basedir exists, if not, create it
    try:
        os.listdir(basedir)
    except os.error:
        os.mkdir(basedir)
        if durability == "sync":
            fileutils.sync_directory(os.path.dirname(os.path.abspath(basedir)))

    # if no snapshot files, create first one with a 'empty' system
    integrity = None
    new_signed = (secret is not None
                  and not fileutils.list_snapshot_files(basedir)
                  and not fileutils.list_log_files(basedir)
                  and not os.path.exists(os.path.join(basedir, IDENTITY_FILE)))
    if new_signed:
        integrity = Integrity.open(basedir, secret, create=True, durability=durability)
    if not fileutils.last_snapshot_file(basedir) and (secret is None or new_signed):
        logger.info(CORE_LOG_PREFIX + "No snapshot files..")
        SnapshotManager(basedir, durability=durability, integrity=integrity).take_snapshot(obj)

    # measure restore time
    start = time.perf_counter()
    logger.info(CORE_LOG_PREFIX + "coopy init....")

    # inject clock on system object
    inject(obj, '_clock', RecordClock())
    inject(obj, '_system_data_path', system_data_path)

    # RestoreHelper will recover a system state based on snapshots and
    # transations files extracting actions executed previously and
    # re-executing them again
    result = recover(obj, basedir, mode=recovery, secret=secret)
    obj = result.system

    delta = time.perf_counter() - start
    logger.info(CORE_LOG_PREFIX + "restore spent %.6f seconds" % delta)

    if secret is not None:
        integrity = Integrity.open(basedir, secret)
    journal = DiskJournal(basedir, system_data_path, durability=durability,
                          integrity=integrity)
    journal.setup()

    snapshot_manager = SnapshotManager(basedir, durability=durability, integrity=integrity)

    proxy = CoopyProxy(obj, [journal], snapshot_manager=snapshot_manager)
    proxy.recovery_report = result.report
    return proxy

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
        # the timer waits snapshot_time before the first snapshot, so this
        # call returns immediately
        self.snapshot_timer = SnapshotTimer(snapshot_time, self)
        self.snapshot_timer.start()

    def start_master(self, port=8012, password=None, ipc=False,
                     host='127.0.0.1'):
        with self.lock:
            if self.slave is not None:
                raise RuntimeError('Cannot promote a slave to master.')
            if self.master is not None:
                raise RuntimeError('Master is already started.')
            self.server = CopyNet(self.obj,
                                  host=host,
                                  port=port,
                                  password=_to_password(password),
                                  ipc=ipc,
                                  lock=self.lock)
            self.publisher.register(self.server)
            self.master = self.server
            self.server.start()

    def start_slave(self, host, port, password=None, ipc=False):
        with self.lock:
            if self.master is not None:
                raise RuntimeError('Cannot start a slave on an active master.')
            if self.slave is not None and self.slave.is_alive():
                raise RuntimeError('Slave receiver is already started; close it first.')
            self.server = None
            # Install the read/write guard before attempting network I/O, so
            # even a failed connection leaves an explicitly unsynchronized slave.
            self.slave = CopyNetSlave(self,
                                      host=host,
                                      port=port,
                                      password=_to_password(password),
                                      ipc=ipc, connect=False)
            self.slave._connect()
            self.slave.start()
            return self.slave

    def __getattr__(self, name):
        if self.slave and not self.slave.synchronized:
            raise RuntimeError('Slave is not synchronized with its master.')
        method =  method_or_none(self.obj, name)

        if not method:
            return getattr(self.obj, name)

        (readonly,unlocked,abort_exception) = action_check(method)

        #TODO: re-write
        if not readonly and hasattr(self, 'slave') and self.slave:
            raise Exception('This is a slave/read-only instance.')

        def method(*args, **kwargs):
            exception = None
            try:
                if not unlocked:
                    self.lock.acquire(1)

                if self.slave and not self.slave.synchronized:
                    raise RuntimeError('Slave is not synchronized with its master.')
                if self.slave and not readonly:
                    raise RuntimeError('This is a slave/read-only instance.')

                #record all calls to clock.now()
                self.obj._clock = RecordClock()

                thread_ident = threading.get_ident()
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
                    exception = e

                #restore clock
                action.results = self.obj._clock.results
                # lets restore tell expected failures from divergences
                action.raised = exception is not None

                if not readonly and not (abort_exception and action.raised):
                    self.publisher.publish(action)

            finally:
                if not unlocked:
                    self.lock.release()

            if exception is not None:
                raise exception

            return system
        return method

    def basedir_abspath(self):
        disk_journals = (journal for journal in self.publisher.subscribers
                                             if hasattr(journal, 'basedir'))
        return [os.path.join(os.path.abspath(os.getcwd()), journal.basedir)
                for journal in disk_journals]

    def take_snapshot(self):
        slave = self.slave
        if slave:
            slave.acquire()
        try:
            self.lock.acquire()
            try:
                if slave and not slave.synchronized:
                    raise RuntimeError('Cannot snapshot an unsynchronized slave.')
                if self.snapshot_manager:
                    for journal in self.publisher.subscribers:
                        if isinstance(journal, DiskJournal):
                            journal.check_writable()
                    def advance_journals(destination):
                        for journal in self.publisher.subscribers:
                            if isinstance(journal, DiskJournal):
                                journal.checkpoint(destination)
                    self.snapshot_manager.take_snapshot(
                        self.obj, before_publish=advance_journals)
            finally:
                self.lock.release()
        finally:
            if slave:
                slave.release()

    def close(self):
        # stop the timer first so no snapshot runs against closed resources
        if self.snapshot_timer:
            self.snapshot_timer.stop()
            self.snapshot_timer = None
        self.publisher.close()
        if self.slave:
            self.slave.close()

    def shutdown(self):
        if self.master:
            self.master.close()
            self.master = None
        if self.slave:
            self.slave.close()
            # Retain the slave role and guard until a fresh bootstrap succeeds.
