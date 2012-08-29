def method_or_none(instance, name):
    method = getattr(instance, name)
    if (name[0:2] == '__' and name[-2,:] == '__') or \
                                    not callable(method) :
        return None
    return method

def action_check(obj):
    return (hasattr(obj, '__readonly'),
            hasattr(obj, '__unlocked'),
            hasattr(obj, '__abort_exception'))

def inject(obj, name, dependency):
    obj.__dict__[name] = dependency
