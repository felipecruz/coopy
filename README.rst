coopy
=====

**coopy** is a simple, transparent, non-intrusive persistence library for python language. It's released under `BSD License`_

* **Simple** - you don't have to learn an API. You can use it with just one line of code.
* **Transparent** - you don't need to call any API functions, just your Object methods.
* **Non-Intrusive** - no inheritance, no interface.. only pure-python-business code.

It is based on the techniques of system snapshotting and transaction journalling. In the prevalent model, the object data is kept in memory in native object format, rather than being marshalled to an RDBMS or other data storage system. A snapshot of data is regularly saved to disk, and in addition to this, all changes are serialised and a log of transactions is also stored on disk.

http://en.wikipedia.org/wiki/Object_prevalence

Status
------

coopy is compatible with py2.6, py2.7, py3.2 and pypy.

CI builds:

.. raw:: html

    <img src="https://secure.travis-ci.org/felipecruz/coopy.png?branch=master" />

Simple, transparent and non-intrusive.

.. code-block:: python

    from coopy.base import init_persistent_system
    from tests.domain import Wiki

    wiki = init_persistent_system(Wiki())

Documentation
-------------

Soon at - http://coopy.readthedocs.org

Contribute
----------

You know!

Fork, Pull Request :)
