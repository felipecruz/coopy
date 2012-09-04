.. _use_clock:

How to Use Clock
================

Date problem
````````````

**coopy** is based on re-execute actions performed in the past. When you call datetime.now() inside an 'business' method, when your actions are executed in restore process, datetime.now() will be executed again. This behaviour will produce unexpected results.

Why use Clock?
``````````````

Clock uses **coopy** timestamp. When you execute a 'business' method, coopy takes the current timestamp and persist inside action object. Clock object has his timestamp updated with action timestamp so in a restore process, Clock will have the original timestamp, and not the timestamp from the re-execution process.


Wrong code::

    def create_page(self, wikipage):
        page = None
        wikipage.last_modify = datetime.now()
        ....

Right code::

    from coopy import clock
    def create_page(self, wikipage):
        page = None
        wikipage.last_modify = clock.now()
        ....
