.. _method_decorators:

Method Decorators
-----------------

@readonly
=========

This decorator means thar your method will not mofidy business objects. Like a get method from a Wiki class. Therefore, this method will not generate a log entry at coopy actions log::

    from coopy.decorators import readonly
    @readonly
    def get_page(self, id):
        if id in self.pages:
            return self.pages[id]
        else:
            return None

@unlocked
=========

How coopy assures thread-safety? By synchronizing method invocations using a reetrant lock.

This decorator provides a means of leaving the thread safety in your hands via the @unlocked decorator. Using this decorator, you should implement concurrency mechanism by yourself.

@abort_exception
================

Default behaviour is to log on disk, even if your code raises an exception.

If your 'business' method raises an exception and your method is decoreted by @abort_exception, this execution will not be logged at disk. This means that during restore process, this invocation that raised an exception will not be re-executed::

    from coopy.decorators import abort_exception
    @abort_exception
    def create_page(self, wikipage):
        page = None
        wikipage.last_modify = coopy.clock.now()
        if wikipage.id in self.pages:
            page = self.pages[wikipage.id]
        if not page:
            self.pages[wikipage.id] = wikipage
            raise Exception('Exemple error')
        else:
            self.update_page(wikipage.id, wikipage.content)


**Restore process will not execute this method because it wasn't logged at disk.**
