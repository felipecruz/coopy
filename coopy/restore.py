import logging
import fileutils

from snapshot import SnapshotManager
from foundation import RestoreClock
from cPickle import Unpickler

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
        unpickler = Unpickler(open(file,'rb'))
        try:
            while True:
                action = unpickler.load()
                logger.debug(LOG_PREFIX + action.action)
                actions.append(action)
        except EOFError:
            pass
            
    if not actions:
        return system
    
    logger.debug(LOG_PREFIX + "Actions re-execution")
    for action in actions:
        try:
            system._clock = RestoreClock(action.timestamps)
            action.execute_action(system)
        except Exception as e:
            logger.debug(LOG_PREFIX + 'Error executing :' + str(action))
        
    system._clock = current_clock
    return system
    
