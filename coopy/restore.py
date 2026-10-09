import logging
from pickle import Unpickler, UnpicklingError

from coopy import fileutils
from coopy.snapshot import SnapshotManager
from coopy.foundation import RestoreClock

logger = logging.getLogger("coopy")
LOG_PREFIX = '[RESTORE] '

def restore(system, basedir):
    #save current clock
    current_clock = system._clock

    #restore from snapshot
    system = SnapshotManager(basedir).recover_snapshot()

    files = fileutils.last_log_files(basedir)
    logger.debug(LOG_PREFIX + "Files found: " + str(files))
    if not files:
        return system

    actions = []
    for file in files:
        logger.debug(LOG_PREFIX + "Opening  " + str(file))
        with open(file, 'rb') as journal_file:
            unpickler = Unpickler(journal_file)
            try:
                while True:
                    action = unpickler.load()
                    logger.debug(LOG_PREFIX + action.action)
                    actions.append(action)
            except EOFError:
                pass
            except (UnpicklingError, AttributeError, ImportError,
                    IndexError, ValueError) as e:
                # a truncated or corrupted journal: keep what was read so
                # far, but make the data loss visible
                logger.error(LOG_PREFIX + "Error unpickling %s after %d "
                             "actions: %r" % (file, len(actions), e))

    if not actions:
        return system

    logger.debug(LOG_PREFIX + "Actions re-execution")
    for action in actions:
        try:
            system._clock = RestoreClock(getattr(action, 'results', None)
                                         or [])
            action.execute_action(system)
        except Exception as e:
            raised = getattr(action, 'raised', None)
            if raised:
                # it also failed when it first ran, replay matches
                log = logger.debug
            elif raised is None:
                # journal written before coopy 0.5 - can't tell
                log = logger.warning
            else:
                # it succeeded originally: restored state diverged
                log = logger.error
            log(LOG_PREFIX + 'Error executing: %s' % (str(action)))
            log(LOG_PREFIX + 'Exception: %r' % (e,))

    system._clock = current_clock
    return system
