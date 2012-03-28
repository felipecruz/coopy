def unlocked(func):
    func.__unlocked = True
    return func

def readonly(func):
    func.__readonly = True
    return func

def abort_exception(func):
    func.__abort_exception = True
    return func