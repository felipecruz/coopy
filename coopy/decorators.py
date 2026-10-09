def unlocked(func):
    func.__unlocked = True
    return func

def readonly(func):
    func.__readonly = True
    return func

def abort_exception(func):
    """Skip journaling failed calls; successful non-readonly calls are recorded.

    Exceptions still reach the caller. This does not roll back in-memory
    mutations or external effects, and later snapshots can retain mutations
    made before a failure. Combined with readonly, neither outcome is recorded.
    """
    func.__abort_exception = True
    return func
