from datetime import datetime

class RecordClock(object):
    def __init__(self):
        self.timestamps = []

    def now(self):
        dt = datetime.now()
        self.timestamps.append(dt)
        return dt

class RestoreClock(object):
    def __init__(self, timestamps):
        #reverse order!
        self.timestamps = timestamps[::-1]

    def now(self):
        return self.timestamps.pop()

class Action(object):
    def __init__(self, caller_id, action, timestamp, args, kwargs):
        self.caller_id = caller_id
        self.action = action
        self.args = args
        self.kwargs = kwargs
        self.timestamps = [timestamp]

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
