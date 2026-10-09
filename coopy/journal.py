import os
import pickle
from pickle import Pickler

from coopy import fileutils

class DiskJournal():
    def __init__(self, basedir, system_data_path):
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
        self.file = self.current_journal_file(self.basedir)
        self.pickler = Pickler(self.file, pickle.HIGHEST_PROTOCOL)
        self.file.set_pickler(self.pickler)

    def current_journal_file(self, basedir):
        # Never append a fresh pickler's memo to an existing pickle stream.
        # Also guarantees that reopened journals follow the latest snapshot.
        return fileutils.RotateFileWrapper(
            open(fileutils.next_log_file(fileutils.name_to_dir(self.basedir)), 'xb'),
            self.basedir, self.system_data_path)

    def checkpoint(self, snapshot_path):
        """Advance past a reserved checkpoint before it becomes visible.

        The caller holds the domain lock. If publication subsequently fails,
        all old journals remain available for replay from the old checkpoint.
        """
        number = fileutils.get_number(os.path.basename(snapshot_path)) + 1
        number = max(number, fileutils.next_number(self.basedir))
        self.file.rotate(fileutils.to_log_file(
            fileutils.name_to_dir(self.basedir), number))

    def receive_before(self, message):
        pass

    def receive(self, message):
        '''
            receive a message and pickle
        '''
        self.pickler.dump(message)
        # A Pickler can call write more than once per record. Rotating inside
        # write splits large records and clears a memo still in use by dump.
        self.file.rotate_if_needed()

    def receive_exception(self, message):
        pass

    def close(self):
        '''
            close file instance
        '''
        if not self.file.closed:
            self.file.close()
