# coopy

**coopy** is a simple, transparent, non-intrusive persistence library for python language. It's released under BSD License

* **Simple** - you don't have to learn an API. You can use it with just one line of code.
* **Transparent** - you don't need to call any API functions, just your Object methods.
* **Non-Intrusive** - no inheritance, no interface.. only pure-python-business code.

It is based on the techniques of system snapshotting and transaction journalling. In the prevalent model, the object data is kept in memory in native object format, rather than being marshalled to an RDBMS or other data storage system. A snapshot of data is regularly saved to disk, and in addition to this, all changes are serialised and a log of transactions is also stored on disk.

http://en.wikipedia.org/wiki/Object_prevalence

## Status

Current version - 0.4.1beta

coopy is compatible with py2.6, py2.7, py3.2, py3.3 and pypy.

CI builds:

[![Build Status](https://secure.travis-ci.org/felipecruz/coopy.png)](http://travis-ci.org/felipecruz/coopy)

## Install

```sh
$ pip install coopy
```

or


```sh
$ git clone https://github.com/felipecruz/coopy.git
$ cd coopy
$ python setup.py install
```

## Using

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

## Restrictions

This should not affect end-user code

To get datetime or date objects you need to get from an internal clock.
Check [How to use Clock](http://coopy.readthedocs.org/en/latest/use_clock.html)

## Documentation

http://coopy.readthedocs.org

## Cases

### RioBus

http://riobus.loogica.net/

All (~1800) Bus lines from RJ (State), Brazil, each Bus Line with a list
of tuples (street, city_name, direction). All in memory. Running since Sep 2012.

System(Domain) Class: https://github.com/loogica/riobus/blob/master/riobus.py

## Tests

First time:

`pip install -r requirements.txt`

To actually run the tests:

`make test`

## Coverage Report

First time:

`pip install -r requirements.txt`

And then:

`make coverage`

# LICENSE

```
Copyright (c) 2009/2012, Loogica - Felipe João Pontes da Cruz - felipecruz@loogica.net
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice, 
       this list of conditions and the following disclaimer.
    
    2. Redistributions in binary form must reproduce the above copyright 
       notice, this list of conditions and the following disclaimer in the
       documentation and/or other materials provided with the distribution.

    3. Neither the name of copycat nor the names of its contributors may be used
       to endorse or promote products derived from this software without
       specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

Contribute
----------

You know!

Fork, Pull Request :)

Contact
-------

felipecruz@loogica.net
