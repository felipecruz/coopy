import os
import pickle
import threading
from pathlib import Path
from pickle import Pickler

from coopy import fileutils
from coopy.error import ConfigurationError
from coopy.error import PersistenceError as PersistenceError


class DiskJournal:
    def __init__(
        self, basedir, system_data_path, durability="buffered", integrity=None, serializer=None
    ):
        self.serializer = serializer
        self.integrity = integrity
        if durability not in ("buffered", "sync"):
            raise ConfigurationError("durability must be 'buffered' or 'sync'")
        self.durability = durability
        self.failure = None
        self.condition = None
        self.group_commit_delay = 0.0
        self.pending = 0
        self.synchronized = 0
        self.sync_leader = False
        """
            set basedir and declare file attribute
        """
        self.basedir = Path(basedir)
        self.file = None
        self.system_data_path = system_data_path

    def setup(self):
        """
        configure file attribute, create pickler
        """
        try:
            self.file = self.current_journal_file(self.basedir)
            self.pickler = (
                Pickler(self.file, pickle.HIGHEST_PROTOCOL)
                if self.serializer is None
                else self.serializer.writer(self.file)
            )
            self.file.set_pickler(self.pickler)
        except Exception as error:
            self._failed(error)

    def current_journal_file(self, basedir):
        # Never append a fresh pickler's memo to an existing pickle stream.
        # Also guarantees that reopened journals follow the latest snapshot.
        file = open(fileutils.next_log_file(self.basedir), "xb")
        try:
            if self.durability == "sync":
                fileutils.sync_directory(self.basedir)
            return fileutils.RotateFileWrapper(
                file, self.basedir, self.system_data_path, durability=self.durability
            )
        except BaseException:
            file.close()
            raise

    def checkpoint(self, snapshot_path):
        """Advance past a reserved checkpoint before it becomes visible.

        The caller holds the domain lock. If publication subsequently fails,
        all old journals remain available for replay from the old checkpoint.
        """
        number = fileutils.get_number(os.path.basename(snapshot_path)) + 1
        number = max(number, fileutils.next_number(self.basedir))
        self.file.rotate(fileutils.to_log_file(self.basedir, number))
        self._acknowledge()

    def enable_group_commit(self, lock, delay):
        if self.durability == "sync" and delay > 0:
            self.condition = threading.Condition(lock)
            self.group_commit_delay = delay

    def _acknowledge(self):
        self.synchronized = self.pending
        if self.condition is not None:
            self.condition.notify_all()

    def sync_pending(self):
        """Synchronize under the domain lock; never acknowledge a failed batch."""
        self.check_writable()
        if self.pending > self.synchronized:
            try:
                self.file.flush()
                self.file.rotate_if_needed()
            except Exception as error:
                self._failed(error)
            self._acknowledge()

    def wait_sync(self):
        """Caller holds the domain lock; waiting releases it for other writers."""
        if self.condition is None:
            return
        target = self.pending
        while target > self.synchronized:
            self.check_writable()
            if self.sync_leader:
                self.condition.wait()
            else:
                self.sync_leader = True
                try:
                    self.condition.wait(self.group_commit_delay)
                    # Close/checkpoint may have synchronized this batch already.
                    if target > self.synchronized:
                        self.sync_pending()
                finally:
                    self.sync_leader = False
                    self.condition.notify_all()

    def _failed(self, error):
        self.failure = error
        if self.condition is not None:
            with self.condition:
                self.condition.notify_all()
        raise PersistenceError(
            "Journal persistence failed; memory may already be changed. "
            "No rollback was performed. Stop using this proxy and inspect recovery."
        ) from error

    def check_writable(self):
        if self.failure is not None:
            raise PersistenceError(
                "Journal is failed; memory may already be changed. "
                "Further mutations and checkpoints are disabled."
            ) from self.failure
        if self.file is None or self.file.closed:
            raise PersistenceError("Journal is not open; mutation refused.")

    def receive_before(self, message):
        self.check_writable()

    def receive(self, message):
        """
        receive a message and pickle
        """
        self.check_writable()
        try:
            if self.integrity is None:
                self.pickler.dump(message)
            else:
                payload = (
                    pickle.dumps(message, pickle.HIGHEST_PROTOCOL)
                    if self.serializer is None
                    else self.serializer.dumps(message)
                )
                self.file.write(self.integrity.encode(payload, self.file.name, self.file.tell()))
            self.pending += 1
            if self.condition is not None:
                return
            if self.durability == "sync":
                # Acknowledge only after the entire record is flushed/synced.
                self.file.flush()
            # Rotate only between records, never during Pickler.dump().
            self.file.rotate_if_needed()
            self.synchronized = self.pending
        except Exception as error:
            self._failed(error)

    def receive_exception(self, message):
        pass

    def close(self):
        """
        close file instance
        """
        if self.file is not None and not self.file.closed:
            try:
                self.file.close()
            except Exception as error:
                self._failed(error)
