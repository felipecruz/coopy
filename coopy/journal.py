import six
import os
import pickle
from coopy import fileutils

if six.PY3:
    from pickle import Pickler
else:
    from cPickle import Pickler

class DiskJournal():
    def __init__(self, basedir):
        '''
            set basedir and declare file attribute
        '''
        self.basedir = basedir
        self.file = None

    def setup(self):
        '''
            configure file attribute, create pickler
        '''
        self.file = self.current_journal_file(self.basedir)
        self.pickler = Pickler(self.file, pickle.HIGHEST_PROTOCOL)
        self.file.set_pickler(self.pickler)

    def current_journal_file(self, basedir):
        '''
            get current file on basedir(last created one)
            and return a Rotate wrapper.

            if current file size > 1Mb (configured on fileutils) crate
            another file with the next name
        '''

        last_file_name = fileutils.last_log_file(self.basedir)

        if last_file_name and os.path.getsize(self.basedir + last_file_name) \
            < fileutils.MAX_LOGFILE_SIZE:

            file = fileutils.RotateFileWrapper(
                        open(self.basedir + last_file_name, 'ab'),
                        self.basedir
                    )
        else:
            file = fileutils.RotateFileWrapper(
                        open(fileutils.next_log_file(self.basedir), 'wb'),
                        self.basedir
                    )

        return file

    def receive_before(self, message):
        pass

    def receive(self, message):
        '''
            receive a message and pickle
        '''
        self.pickler.dump(message)

    def receive_exception(self, message):
        pass

    def close(self):
        '''
            close file instance
        '''
        if not self.file.closed:
            self.file.close()
