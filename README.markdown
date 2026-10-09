# coopy

[![CI](https://github.com/felipecruz/coopy/actions/workflows/ci.yml/badge.svg)](https://github.com/felipecruz/coopy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/coopy.svg)](https://pypi.org/project/coopy/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)](LICENSE)

**Persistence for plain Python objects. No database, no ORM, no schema - one line of code.**

```python
from coopy.base import init_persistent_system

todo = init_persistent_system(TodoList)   # that's the whole integration
todo.add("write the README")              # this change is now durable
```

Restart your program, and your `TodoList` is exactly where you left it.

## Why coopy

- **One line.** Wrap your object once. Keep calling its methods as usual.
- **Your code stays yours.** No base class, no decorators required, no
  mapping layer. Your domain classes are plain Python.
- **Memory speed.** Reads are ordinary attribute access - no queries, no
  network round trips, no serialization.
- **Full history.** Every change is a journal entry, so state can always be
  rebuilt by replaying what happened.
- **Thread-safe by default.** Method calls are serialized for you.
- **Replication built in.** Stream changes to read-only replicas over TCP or
  Unix sockets.

## The idea: object prevalence

Most applications load data from a database, change it, and write it back.
coopy flips this around: **your objects live in memory, and the disk is just
a log.** This technique is called
[object prevalence](https://en.wikipedia.org/wiki/System_prevalence).

1. **Every change is a method call.** coopy wraps your object in a proxy.
   When you call a method that changes state, the call itself - method name
   and arguments - is appended to a journal on disk.
2. **Snapshots save time.** Now and then the whole object is saved as a
   snapshot, so the journal doesn't grow forever.
3. **Restart = snapshot + replay.** On startup coopy loads the latest snapshot
   and re-runs the journaled calls made after it. Same calls, same order,
   same state.

```
 your code ──► proxy ──► your object (in memory)
                 │
                 └──► journal: add("milk"), add("eggs"), done(0), ...

 restart:  latest snapshot ──► replay journal ──► same object as before
```

The tradeoff: your data has to fit in memory. For a huge range of apps -
internal tools, games, bots, prototypes, configuration and catalog services -
it does, and you get a much simpler stack in exchange.

## Quick start

```sh
pip install coopy
```

```python
from coopy.base import init_persistent_system
from coopy.decorators import readonly

class TodoList(object):
    def __init__(self):
        self.items = []

    def add(self, text):
        self.items.append({"text": text, "done": False,
                           "created": self._clock.now()})

    def done(self, index):
        self.items[index]["done"] = True

    @readonly
    def pending(self):
        return [item["text"] for item in self.items if not item["done"]]

todo = init_persistent_system(TodoList)
todo.add("buy milk")
todo.add("write the README")
todo.done(0)
print(todo.pending())   # ['write the README'] - also after a restart
todo.close()
```

Data is stored in a directory named after your class (`todolist/` here).
Pass `basedir="some/dir"` to choose another location.

## The rules

Replaying calls only works if they give the same result the second time.
That means:

- **Change state only through methods** called on the wrapped object. If you
  modify an object returned by a method directly, that change is not
  journaled.
- **Use `self._clock` for time.** Call `self._clock.now()`, `utcnow()` or
  `today()` instead of `datetime.now()`. coopy records the value and hands
  back the same one on replay. coopy rejects classes that call
  `datetime.now()` directly.
- **No other outside input inside methods** - no random numbers, network
  calls or file reads. Do those outside and pass the results in as
  arguments.
- **Arguments and state must be picklable.**

## More features

**Decorators** fine-tune individual methods:

| Decorator | Effect |
| --- | --- |
| `@readonly` | Not journaled. Use for queries. |
| `@abort_exception` | If the method raises, the call is not journaled. |
| `@unlocked` | Skips coopy's lock; you handle thread safety yourself. |

**Snapshots** keep restarts fast:

```python
todo.take_snapshot()               # take one now
todo.start_snapshot_manager(3600)  # or every hour, in the background
```

**Replication** streams every change to read-only replicas:

```python
# primary
todo.start_master(port=8012, password="secret")

# replica, started from a copy of the primary's state
replica.start_slave("primary-host", 8012, password="secret")
```

## Good to know

- **Security:** journals, snapshots and replication use `pickle`, which can
  run arbitrary code when loaded. Only restore data directories you trust,
  and only replicate between trusted hosts on a trusted network.
- **Durability:** each change is written and flushed to the journal as soon
  as the call completes, so it survives a crash of your program. coopy does
  not `fsync` every write, so a power failure can lose the most recent
  changes.
- **Python:** 3.10 or newer. Python 2 support ended with coopy 0.4.x.

## Used in production

[RioBus](https://github.com/loogica/riobus) kept every bus line in the state
of Rio de Janeiro - about 1,800 lines with their full routes - in memory with
coopy, running since September 2012.

## Documentation

Full docs: http://coopy.readthedocs.org

## Development

```sh
git clone https://github.com/felipecruz/coopy.git
cd coopy
pip install -e ".[test]"
make test       # run the tests
make coverage   # HTML coverage report in htmlcov/
```

Contributions are welcome - fork the repo and open a pull request.

## License

BSD 3-Clause. See [LICENSE](LICENSE).

Contact: felipecruz@loogica.net
