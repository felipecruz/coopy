coopy
-----

**coopy** is a simple, transparent, non-intrusive persistence library for python language. It's released under `BSD License`_

 * **Simple** - you don't have to learn an API. You can use it with just one line of code.
 * **Transparent** - you don't need to call any API functions, just your Object methods.
 * **Non-Intrusive** - no inheritance, no interface.. only pure-python-business code.

It is based on the techniques of system snapshotting and transaction journalling. In the prevalent model, the object data is kept in memory in native object format, rather than being marshalled to an RDBMS or other data storage system. A snapshot of data is regularly saved to disk, and in addition to this, all changes are serialised and a log of transactions is also stored on disk.

http://en.wikipedia.org/wiki/Object_prevalence

Simple, transparent, non-intrusive::

    from coopy.base import init_persistent_system
    from tests.domain import Wiki

    wiki = init_persistent_system(Wiki())

Check out how coopy works with this little :doc:`tutorial` and then...

It's very important to know how coopy works, to use it. Check out :doc:`basics`

contribute
----------

**coopy** code is hosted on github at: http://github.com/felipecruz/coopy

Found a bug? http://github.com/felipecruz/coopy
