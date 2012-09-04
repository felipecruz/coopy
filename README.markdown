coopy
=====

**coopy** is a simple, transparent, non-intrusive persistence library for python language. It's released under BSD License

* **Simple** - you don't have to learn an API. You can use it with just one line of code.
* **Transparent** - you don't need to call any API functions, just your Object methods.
* **Non-Intrusive** - no inheritance, no interface.. only pure-python-business code.

It is based on the techniques of system snapshotting and transaction journalling. In the prevalent model, the object data is kept in memory in native object format, rather than being marshalled to an RDBMS or other data storage system. A snapshot of data is regularly saved to disk, and in addition to this, all changes are serialised and a log of transactions is also stored on disk.

http://en.wikipedia.org/wiki/Object_prevalence

Status
------

coopy is compatible with py2.6, py2.7, py3.2 and pypy.

CI builds:

[![Build Status](https://secure.travis-ci.org/felipecruz/coopy.png)](http://travis-ci.org/felipecruz/coopy)

Using
-----

Simple, transparent and non-intrusive. Note that ``Todo`` could be any class
that you want to persist state across method calls that modifies it's internal
state.

```python

from coopy.base import init_persistent_system
class Todo(object):
    def __init__(self):
        self.tasks = []

    def add_task(self, name, description):
        task = dict(name=name, description=description)
        self.tasks.append(task)

persistent_todo_list = init_persistent_system(Todo())
persistent_todo_list.add_task("Some Task Name", "A Task Description")
```

Documentation
-------------

Soon at - http://coopy.readthedocs.org

Tests
-----

First time:

`pip install -r requirements.txt`

To actually run the tests:

`make test`

Coverage Report
---------------

First time:

`pip install -r requirements.txt`

And then:

`make coverage`


Contribute
----------

You know!

Fork, Pull Request :)

Contact
-------

felipecruz@loogica.net
