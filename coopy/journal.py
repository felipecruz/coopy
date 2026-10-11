import os
import pickle
import threading
from contextvars import ContextVar
from pathlib import Path
from pickle import Pickler

from coopy import fileutils
from coopy.error import ConfigurationError
from coopy.error import PersistenceError as PersistenceError

# set while a @transactional call publishes: a record that fails before it is
# complete on disk is cut off again so the rolled-back call is never replayed
discard_failed_record: ContextVar[bool] = ContextVar("coopy_discard", default=False)


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
        # offset of a failed record that was cut off the journal again
        self.discarded_at = None
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

    def _failed(self, error, discarded=False):
        self.failure = error
        if self.condition is not None:
            with self.condition:
                self.condition.notify_all()
        if discarded:
            failure = PersistenceError(
                "Journal persistence failed; the record was removed from the journal. "
                "Memory may already be changed unless the method is @transactional. "
                "Stop using this proxy and inspect recovery."
            )
        else:
            failure = PersistenceError(
                "Journal persistence failed; memory may already be changed. "
                "No rollback was performed. Stop using this proxy and inspect recovery."
            )
        # lets @transactional calls roll back only records that are not on disk
        failure.record_discarded = discarded
        raise failure from error

    def _discard(self, offset):
        """Cut a failed record off the journal; True once the cut is durable."""
        if offset is None or not discard_failed_record.get():
            return False
        try:
            fd = self.file.fileno()
            os.ftruncate(fd, offset)
            if self.durability == "sync":
                os.fsync(fd)
        except Exception:
            return False
        # close() may still write the failed record's buffered bytes
        self.discarded_at = (self.file.name, offset)
        return True

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
        offset = None
        written = False
        try:
            offset = self.file.tell()
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
            written = True
            # Rotate only between records, never during Pickler.dump().
            self.file.rotate_if_needed()
            self.synchronized = self.pending
        except Exception as error:
            # a record that reached the file intact stays; it may be replayed
            self._failed(error, discarded=not written and self._discard(offset))

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
            finally:
                if self.discarded_at is not None:
                    self._cut_again()

    def _cut_again(self):
        # Closing flushes buffered bytes of the discarded record, if any.
        name, offset = self.discarded_at
        self.discarded_at = None
        if os.path.getsize(name) > offset:
            os.truncate(name, offset)
            if self.durability == "sync":
                fd = os.open(name, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
