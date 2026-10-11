# coopy

[![CI](https://github.com/felipecruz/coopy/actions/workflows/ci.yml/badge.svg)](https://github.com/felipecruz/coopy/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/felipecruz/coopy/branch/main/graph/badge.svg)](https://app.codecov.io/gh/felipecruz/coopy/tree/main)
[![PyPI](https://img.shields.io/pypi/v/coopy.svg)](https://pypi.org/project/coopy/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)](LICENSE)

**Persistence for plain Python objects. No database, no ORM, no schema - one line of code.**

```python
from coopy.base import init_persistent_system

todo = init_persistent_system(TodoList)   # that's the whole integration
todo.add("write the README")              # journal this change
```

Reopen the same data directory to restore your `TodoList` from its snapshot
and journal, provided your methods replay deterministically and storage is intact.

## Why coopy

- **One line.** Wrap your object once. Keep calling its methods as usual.
- **Your code stays yours.** No base class, no decorators required, no
  mapping layer. Your domain classes are plain Python.
- **Memory speed.** Reads are ordinary attribute access - no queries, no
  network round trips, no serialization.
- **Journaled methods.** Recover recorded changes by replaying method calls
  after the latest snapshot.
- **Typed.** `init_persistent_system(TodoList)` returns a `TodoList` to your
  type checker, so editors autocomplete methods and mypy checks arguments.
- **Serialized calls.** Method calls through the proxy take a lock by default.
- **Experimental replication.** Bootstrap read-only replicas and stream
  subsequent changes over TCP or Unix sockets.

## The idea: object prevalence

Most applications load data from a database, change it, and write it back.
coopy flips this around: **your objects live in memory, and the disk is just
a log.** This technique is called
[object prevalence](https://en.wikipedia.org/wiki/System_prevalence).

1. **Every change is a method call.** coopy wraps your object in a proxy.
   When you call a method that changes state, the call itself - method name
   and arguments - is appended to a journal on disk.
2. **Snapshots save time.** Request or schedule a snapshot of the whole object
   to reduce replay work. Old snapshots and journals are retained; there is no
   automatic pruning.
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
python -m pip install coopy
```

Requires Python 3.10 or newer. Save your domain class in `todo_domain.py` so
another process can import it during recovery:

```python
from coopy.decorators import readonly

class TodoList:
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
```

From the same directory, run this once to create and reopen a persistent list:

```python
from coopy.base import init_persistent_system
from todo_domain import TodoList

todo = init_persistent_system(TodoList)
try:
    todo.add("buy milk")
    todo.add("write the README")
    todo.done(0)
    print(todo.pending())   # ['write the README'] on the first run
finally:
    todo.close()

todo = init_persistent_system(TodoList)
try:
    print(todo.pending())   # the same list, recovered from disk
finally:
    todo.close()
```

Data is stored in a directory named after your class (`todolist/` here).
Pass `basedir="some/dir"` to choose another location; its parent must exist.
Use one process and one persistent proxy per data directory: a writable open
locks the directory, and a second one raises `LockError` until the first is
closed (network filesystems may not honor the lock). The directory's
`coopy.json` manifest records its format version, serializer and signing, and
reopening with different settings or with an older coopy than the format needs
raises `FormatError` before anything is decoded. Stop writers
before closing. Closing does not take a snapshot. Running the writes above
again adds more items to the existing list.

## The rules

Replaying calls only works if they give the same result the second time.
That means:

- **Change state only through methods** called on the wrapped object. If you
  modify an object returned by a method directly, that change is not
  journaled.
- **Use `self._clock` for time.** Call `self._clock.now()`, `utcnow()` or
  `today()` instead of `datetime.now()`. coopy records the value and hands
  back the same one on replay. Source validation flags direct clock, `time`,
  `random`, `uuid`, `os.urandom` and `secrets` calls (pass
  `validation="strict"` to reject them all at open time), but cannot prove
  that your methods are deterministic.
- **Use `self._env` for random values.** `self._env.random()`, `randint()`,
  `choice()`, `shuffle()`, `uuid4()`, `token_hex()` and friends are recorded
  and replayed like the clock (annotate `_env: coopy.Env`). Recorded tokens
  are stored in the journal, so keep real secrets out of it.
- **No other outside input inside methods** - no network calls or file reads.
  Do those outside and pass the results in as arguments.
- **Arguments and state must be picklable.**

## Type hints

coopy ships type information (`py.typed`). The proxy is typed as your domain
class, decorators keep method signatures, and persistence controls go
through `coopy.control()` so they don't clash with your own method names:

```python
# todo_domain.py
from datetime import datetime
from typing import TypedDict

import coopy
from coopy.decorators import readonly


class Item(TypedDict):
    text: str
    done: bool
    created: datetime


class TodoList:
    _clock: coopy.Clock  # injected by coopy

    def __init__(self) -> None:
        self.items: list[Item] = []

    def add(self, text: str) -> int:
        self.items.append({"text": text, "done": False, "created": self._clock.now()})
        return len(self.items) - 1

    def done(self, index: int) -> None:
        self.items[index]["done"] = True

    @readonly
    def pending(self) -> list[str]:
        return [item["text"] for item in self.items if not item["done"]]
```

```python
# app.py
import coopy
from todo_domain import TodoList

with coopy.control(coopy.open(TodoList, "data")) as todo:  # todo: TodoList
    todo.done(todo.add("buy milk"))
    print(todo.pending())                                    # list[str]
    todo.add(42)  # mypy: incompatible type "int"; expected "str"
```

`coopy.open` is an alias of `init_persistent_system`. `coopy.control(todo)`
gives typed access to `take_snapshot()`, `close()`, `start_snapshot_manager()`
and replication, and works as a context manager. `recovery="salvage"` is typed
as `RecoveryResult[TodoList]`. See the
[typed API guide](docs/modern-api.rst) for details and current limits.

## More features

**Decorators** fine-tune individual methods:

| Decorator | Effect |
| --- | --- |
| `@readonly` | Not journaled. Use for queries. |
| `@abort_exception` | If the method raises, the call is not journaled. No rollback is performed. |
| `@transactional` | If the method raises, its changes are rolled back and the call is not journaled. Copies the whole state on every call. |
| `@unlocked` | Skips coopy's lock; you handle thread safety yourself. |

**Snapshots** keep restarts fast:

```python
todo = init_persistent_system(TodoList)
try:
    todo.take_snapshot()               # take one now
    todo.start_snapshot_manager(3600)  # first background snapshot after an hour
    # Run your application here.
finally:
    todo.close()                       # stops the snapshot timer
```

**Replication** is experimental. A new replica receives the primary's state
and queued actions before becoming readable. From a source checkout, run the
[complete local example](docs/examples/replication.py):

```sh
python docs/examples/replication.py
```

Wait for `connection.wait_until_synchronized(timeout=10)` before querying a
replica, and handle a false result. Replication is asynchronous and does not
provide durable replica journaling, automatic reconnect, or failover. See the
[replication guide](docs/replication.rst) for lifecycle and protocol limits.

## Recovery and durability

`init_persistent_system` defaults to `recovery="strict"` and
`durability="buffered"`. Strict recovery raises `coopy.restore.RecoveryError`
on detected corruption or replay divergence; the exception's `report` identifies
where replay stopped. A recovered proxy exposes `recovery_report`.

Buffered writes flush to the operating system, but do not sync every action to
disk. For per-action `os.fsync` before acknowledgment, open with:

```python
todo = init_persistent_system(TodoList, durability="sync")
```

Choose the policy on each open and close the proxy as above. Synchronous mode
requires POSIX directory-sync support and remains subject to filesystem and
device guarantees. A `coopy.journal.PersistenceError` can occur after memory
has changed or a record has persisted; there is no rollback. Stop writers and
inspect recovery before retrying a failed mutation.

For explicit inspection of damaged, trusted storage, `recovery="salvage"`
returns a `RecoveryResult` containing `system` and `report`, rather than a
writable proxy. It stops at the first defect and does not modify persistence
files. Preserve a backup first; salvage is not a repair operation. Read the
[persistence and recovery guide](docs/usage.rst) for the full contract.

## Good to know

- **Security:** journals, snapshots and replication use `pickle`, which can
  run arbitrary code when loaded. Only restore data directories you trust,
  and only replicate between trusted hosts on a trusted network.
- **Replay:** keep external effects outside journaled methods; recovery can
  execute those methods again. Use compatible, importable domain classes.
- **Python:** 3.10 or newer. Python 2 support ended with coopy 0.4.x.

## Documentation

Full docs: http://coopy.readthedocs.org

The checkout includes an [executable tutorial](docs/tutorial.rst),
[decorator semantics](docs/method_decorators.rst), and
[checkpoint guarantees](docs/snapshots.rst).

## Development

```sh
git clone https://github.com/felipecruz/coopy.git
cd coopy
python -m pip install -e ".[test,docs]"
python -m pytest --verbose -W error::DeprecationWarning
python -m pytest --cov-report html --cov coopy  # report in htmlcov/
python -m sphinx -W --keep-going -b html docs build/docs
```

Open `build/docs/index.html` for the local guide. See
[testing documentation](docs/tests.rst) for focused example checks. `make test`
also runs the tests, but first removes build outputs, coverage reports, and
coopy logs through `make clean`.

Contributions are welcome - fork the repo and open a pull request.

## License

BSD 3-Clause. See [LICENSE](LICENSE).

Contact: felipecruz@gmail.com
