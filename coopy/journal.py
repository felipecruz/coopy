import os
import pickle
from pickle import Pickler

from coopy import fileutils

class PersistenceError(RuntimeError):
    """Persistence did not complete; memory may already have changed."""


class DiskJournal():
    def __init__(self, basedir, system_data_path, durability="buffered"):
        if durability not in ("buffered", "sync"):
            raise ValueError("durability must be 'buffered' or 'sync'")
        self.durability = durability
        self.failure = None
        '''
            set basedir and declare file attribute
        '''
        self.basedir = basedir
        self.file = None
        self.system_data_path = system_data_path

    def setup(self):
        '''
            configure file attribute, create pickler
        '''
        try:
            self.file = self.current_journal_file(self.basedir)
            self.pickler = Pickler(self.file, pickle.HIGHEST_PROTOCOL)
            self.file.set_pickler(self.pickler)
        except Exception as error:
            self._failed(error)

    def current_journal_file(self, basedir):
        # Never append a fresh pickler's memo to an existing pickle stream.
        # Also guarantees that reopened journals follow the latest snapshot.
        file = open(fileutils.next_log_file(fileutils.name_to_dir(self.basedir)), 'xb')
        try:
            if self.durability == 'sync':
                fileutils.sync_directory(self.basedir)
            return fileutils.RotateFileWrapper(
                file, self.basedir, self.system_data_path, durability=self.durability)
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
        self.file.rotate(fileutils.to_log_file(
            fileutils.name_to_dir(self.basedir), number))

    def _failed(self, error):
        self.failure = error
        raise PersistenceError(
            'Journal persistence failed; memory may already be changed. '
            'No rollback was performed. Stop using this proxy and inspect recovery.'
        ) from error

    def check_writable(self):
        if self.failure is not None:
            raise PersistenceError(
                'Journal is failed; memory may already be changed. '
                'Further mutations and checkpoints are disabled.'
            ) from self.failure
        if self.file is None or self.file.closed:
            raise PersistenceError('Journal is not open; mutation refused.')

    def receive_before(self, message):
        self.check_writable()

    def receive(self, message):
        '''
            receive a message and pickle
        '''
        self.check_writable()
        try:
            self.pickler.dump(message)
            if self.durability == 'sync':
                # Acknowledge only after the entire record is flushed/synced.
                self.file.flush()
            # Rotate only between records, never during Pickler.dump().
            self.file.rotate_if_needed()
        except Exception as error:
            self._failed(error)

    def receive_exception(self, message):
        pass

    def close(self):
        '''
            close file instance
        '''
        if self.file is not None and not self.file.closed:
            try:
                self.file.close()
            except Exception as error:
                self._failed(error)
