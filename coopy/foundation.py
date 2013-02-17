from datetime import datetime, date, time
from time import localtime

from .validation import FORBIDDEN_OBJECTS, DATETIME_FUNCS, DATE_FUNCS

class RecordClock(object):
    def __init__(self):
        self.results = []

    def __getattr__(self, name):
        if name in DATETIME_FUNCS:
            return getattr(datetime, name)
        elif name in DATE_FUNCS:
            return getattr(date, name)
        return object.__getattribute__(self, name)

    def now(self):
        dt = datetime.now()
        self.results.append(dt)
        return dt

    def utcnow(self):
        dt = datetime.utcnow()
        self.results.append(dt)
        return dt

    def today(self):
        dt = date.today()
        self.results.append(dt)
        return dt

class RestoreClock(object):
    def __init__(self, results):
        #reverse order!
        self.results = results[::-1]

    def __getattr__(self, name):
        if name in DATETIME_FUNCS or name in DATE_FUNCS:
            return self.pop_and_check(name)
        return object.__getattribute__(self, name)

    def pop_and_check(self, method_name):
        last_element = self.results[-1]
        if method_name in DATETIME_FUNCS:
            if not isinstance(last_element, datetime):
                raise TypeError("This call returns a %s" %
                                                         (datetime.__class__))
            return lambda: self.results.pop()
        elif method_name in DATE_FUNCS:
            if not isinstance(last_element, date):
                raise TypeError("This call returns a %s" %
                                                         (date.__class__))
            return lambda: self.results.pop()


class Action(object):
    def __init__(self, caller_id, action, timestamp, args, kwargs):
        self.caller_id = caller_id
        self.action = action
        self.args = args
        self.kwargs = kwargs
        self.results = None

        # TODO do we need it?
        self.timestamp = timestamp

    def __str__(self):
        return "action %s \ncaller_id %s \nargs %s" % \
                (self.action, str(self.caller_id), self.args)

    def execute_action(self, system):
        #TODO not reliable
        method = getattr(system, self.action)
        return method(*self.args, **self.kwargs)

class Publisher:
    def __init__(self, subscribers):
        self.subscribers = subscribers

    def register(self, subscriber):
        self.subscribers.append(subscriber)

    def publish(self, message):
        for subscriber in self.subscribers:
            subscriber.receive(message)

    def publish_before(self, message):
        for subscriber in self.subscribers:
            subscriber.receive_before(message)

    def publish_exception(self, message):
        for subscriber in self.subscribers:
            subscriber.receive_exception(message)

    def close(self):
        for subscriber in self.subscribers:
            subscriber.close()
