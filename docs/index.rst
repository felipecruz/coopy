.. coopy documentation master file, created by
   sphinx-quickstart on Tue May 18 18:06:23 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

coopy
-------

**coopy** is a simple, transparent, non-intrusive persistence library for python language. It's released under `BSD License`_

* **Simple** - you don't have to learn an API. You can use it with just one line of code.
* **Transparent** - you don't need to call any API functions, just your Object methods.
* **Non-Intrusive** - no inheritance, no interface.. only pure-python-business code.

It is based on the techniques of system snapshotting and transaction journalling. In the prevalent model, the object data is kept in memory in native object format, rather than being marshalled to an RDBMS or other data storage system. A snapshot of data is regularly saved to disk, and in addition to this, all changes are serialised and a log of transactions is also stored on disk.

http://en.wikipedia.org/wiki/Object_prevalence

Using
-----

Follow the executable :doc:`tutorial` to open a persistent domain, record
mutations and clock values, take a checkpoint, close, and reopen it. Read
:doc:`usage` for the current durability and recovery contract and :doc:`basics`
for the storage model.


Restrictions
------------

This should not affect end-user code. To get datetime or date objects you
need to get from an internal clock. Check this page :doc:`use_clock`

Status
------

coopy requires Python 3.10 or newer.

contribute
----------

**coopy** code is hosted on github at: http://github.com/felipecruz/coopy

Found a bug? http://github.com/felipecruz/coopy

contents
--------

.. toctree::
   :maxdepth: 2

   installation
   tutorial
   usage
   basics
   use_clock
   method_decorators
   snapshots
   util_api
   client_server
   replication
   tests
   roadmap
   changelog
   todo

.. _BSD License: http://www.opensource.org/licenses/bsd-license.php
