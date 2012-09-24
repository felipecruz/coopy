import os
import re
import types
import logging
import logging.config

logger = logging.getLogger("coopy")

DIGITS = 15
MAX_LOGFILE_SIZE = 1024 * 100 * 10 # 1 MB

LOG_PREFIX = "transaction_"
LOG_SUFIX = ".log"

SNAPSHOT_PREFIX = "snapshot_"
SNAPSHOT_SUFIX = ".dat"

SNAPSHOT_REGEX = re.compile("snapshot_(\d{15})\.dat", re.IGNORECASE)
LOG_REGEX = re.compile("transaction_(\d{15})\.log", re.IGNORECASE)
FILE_REGEX = re.compile("(transaction|snapshot)_(\d{15})\..{3}", re.IGNORECASE)

class RotateFileWrapper():
    def __init__(self, file, basedir, max_size=MAX_LOGFILE_SIZE):
        self.file = file
        self.basedir = basedir
        self.max_size = max_size

    def write(self, data):
        self.file.write(data)

        ''' certifies that data will be written - performance issues? '''
        self.file.flush()

        if os.path.getsize(self.file.name) > self.max_size:
            file_name = next_log_file(self.basedir)
            logger.debug("Opening: " + file_name)
            self.file.flush()
            os.fsync(self.file.fileno())
            self.file.close()
            self.file = open(file_name,'wb')
            self.pickler.clear_memo()

    def __getattr__(self, name):
        if name == 'closed':
            return self.file.closed
        elif name == "flush":
            import os
            self.file.flush()
            os.fsync(self.file.fileno())
        else:
            return getattr(self.file, name)

    @property
    def name(self):
        return self.file.name

    def close(self):
        self.file.close()

    def set_pickler(self, pickler):
        self.pickler = pickler

def number_as_string(number):
    s_number = str(number)
    return s_number.zfill(DIGITS)


def list_coopy_files(basedir, regex):
    files = os.listdir(basedir)
    if not files:
        return None
    files = filter(regex.search, files)
    if not files:
        return None
    return sorted(files)


def list_snapshot_files(basedir):
    return list_coopy_files(basedir, SNAPSHOT_REGEX)


def list_log_files(basedir):
    return list_coopy_files(basedir, LOG_REGEX)


def check_files(files):
    if not files:
        return None
    return files[len(files)-1]


def last_snapshot_file(basedir):
    files = list_coopy_files(basedir, SNAPSHOT_REGEX)
    return check_files(files)

def last_log_file(basedir):
    files = list_coopy_files(basedir, LOG_REGEX)
    return check_files(files)

def lastest_snapshot_number(basedir):
    last_file = last_snapshot_file(basedir)
    if not last_file:
        return 1
    number = SNAPSHOT_REGEX.match(last_file)
    return int(number.group(1))


def lastest_log_number(basedir):
    last_file = last_log_file(basedir)
    if not last_file:
        return 1
    number = LOG_REGEX.match(last_file)
    return int(number.group(1))


def to_log_file(basedir, number):
    return basedir + LOG_PREFIX + number_as_string(number) + LOG_SUFIX;


def to_snapshot_file(basedir, number):
    return basedir + SNAPSHOT_PREFIX + number_as_string(number) + SNAPSHOT_SUFIX;


def get_number(filename):
    number = FILE_REGEX.match(filename)
    return int(number.group(2))


def next_number(basedir):
    n1 = lastest_log_number(basedir)
    n2 = lastest_snapshot_number(basedir)
    if n1 > n2:
        return n1+1
    else:
        return n2+1


def next_snapshot_file(basedir):
    number = next_number(basedir)
    return to_snapshot_file(basedir, number)


def next_log_file(basedir):
    number = next_number(basedir)
    return to_log_file(basedir, number)


def last_log_files(basedir):
    files = list_log_files(basedir)
    if not files:
        return None
    cont = 0
    last_snap = lastest_snapshot_number(basedir)
    file_names = []
    for file in files:
        if get_number(file) > last_snap:
            cont += 1
            file_names.append(basedir + file)
    return file_names

def name_to_dir(basedir):
    if len(basedir) > 0:
        basedir = basedir.replace('\\','/')
        if not basedir.endswith('/'):
            basedir += '/'
    else:
        basedir =  './'
    return basedir

def obj_to_dir_name(obj):
    if isinstance(obj, type):
        basedir = obj.__name__.lower()
    else:
        basedir = obj.__class__.__name__.lower()
    return basedir
