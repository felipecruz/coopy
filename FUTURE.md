# coopy — future directions

This document collects ideas that go beyond [ROADMAP.md](ROADMAP.md). The
roadmap tracks concrete, accepted work; everything here is a proposal to
discuss, prototype or reject. Nothing below is scheduled or promised.

It covers three areas:

1. **Modern Python** — type hints, a friendlier API, tooling and performance.
2. **Distribution** — a pluggable transport, a pyzmq backend, failover and
   multi-master writes.
3. **Decentralization** — an ambitious peer-to-peer variant of coopy.

## Guiding principles

Whatever we build should keep what makes coopy worth using:

- **Plain objects, one line.** Users write ordinary classes. Advanced
  features are opt-in and never required for the basic case.
- **Determinism is the contract.** coopy works because replaying the same
  method calls in the same order gives the same state. Every distributed
  design below is really an answer to one question: *how do all nodes agree
  on the order of calls?*
- **Honest guarantees.** Each feature states what it protects against and
  what it doesn't, as the durability and recovery docs already do.

---

## Part 1 — Modern Python

### 1.1 Type hints

The library has no annotations today. The interesting problem is the proxy:
`init_persistent_system(TodoList)` returns a `CoopyProxy`, so editors and
type checkers lose every method of `TodoList`.

Proposal: type the entry point as returning the user's own type, and move
coopy's control methods to a separate handle.

```python
from typing import TypeVar, overload

T = TypeVar("T")

@overload
def init_persistent_system(obj: type[T], basedir: str | os.PathLike[str] | None = None, *,
                           recovery: Literal["strict", "salvage"] = "strict",
                           durability: Literal["buffered", "sync"] = "buffered",
                           secret: bytes | None = None) -> T: ...
@overload
def init_persistent_system(obj: T, basedir: ..., ...) -> T: ...

# control operations live outside the domain namespace
def control(system: object) -> Persistent: ...   # take_snapshot(), close(), start_master(), ...
```

`todo.add("milk")` then autocompletes and type-checks. A separate handle such as
`coopy.control(todo).close()` also fixes a real name clash: the proxy's own
methods win over the domain object's, so a domain class with its own `close()`,
`shutdown()` or `take_snapshot()` method can't be called through coopy today.
The existing `todo.close()` style stays working for compatibility.

Steps:

- Annotate the public API first (`base.py`, `decorators.py`, `error.py`,
  `integrity.py`), then internals.
- Ship a `py.typed` marker so users get the types.
- Make the decorators type-preserving with `ParamSpec`, so `@readonly` doesn't
  erase signatures.
- Run `mypy --strict` (or pyright) in CI on the package, starting lenient and
  tightening per module.
- Stay on `TypeVar` syntax while Python 3.10 and 3.11 are supported; PEP 695
  generics (`def f[T](...)`) need 3.12+.

### 1.2 API ergonomics

- **Context manager:** `with coopy.open(TodoList, "data/") as todo: ...`
  closes journals and stops the snapshot timer on exit, even on errors.
- **`coopy.open()` as the short entry point**, keeping
  `init_persistent_system` as an alias.
- **`pathlib` everywhere.** Accept `str | os.PathLike` for `basedir` and use
  `Path` internally instead of joining strings, so paths behave the same on
  every OS.
- **primary/replica naming.** Rename `start_master`/`start_slave` to
  `start_primary`/`start_replica`, keeping the old names as deprecated
  aliases for a release or two.
- **A real exception hierarchy.** Some paths still `raise Exception(...)`;
  give each failure a `CoopyError` subclass so callers can catch precisely.
- **Logging without side effects.** `init_persistent_system` still installs a
  file handler that writes `coopy.log` to the working directory. Libraries
  normally leave handler setup to the application; make the file log opt-in.

### 1.3 Serialization and schema evolution

Today journals and snapshots are pickles of the user's classes. Two problems
follow:

- **Renaming or moving a class breaks old data.** Pickle stores the import
  path, so `myapp.models.Todo` → `myapp.todo.Todo` makes every snapshot
  unloadable.
- **Pickle is unsafe across trust boundaries** (partly mitigated by the HMAC
  integrity option, F14).

Ideas:

- **Pluggable serializer** with pickle as the default and an opt-in safe
  format (msgpack or JSON with a registry of allowed types).
- **Versioned actions and upcasters.** Store a schema version with each
  journal record; let users register functions that upgrade old records
  (`add(text)` → `add(text, priority=0)`) when the method signature changes.
- **Class aliases** for renamed classes during unpickling.

### 1.4 Performance

- **Group commit.** With `durability="sync"`, each write currently waits for
  its own fsync. Batching the fsync for calls that arrive together keeps the
  same guarantee with far more writes per second.
- **Fork-based snapshots.** Snapshotting pickles the whole object under the
  lock, pausing writes. On POSIX, `os.fork()` gives the child a copy-on-write
  view of memory, so it can write the snapshot while the parent keeps serving
  writes. This is how Redis does `BGSAVE`. It needs care: fork in a threaded
  process is only safe if the child does nothing but serialize and exit.
- **Snapshot compression** (zstd/lz4 as optional extras).
- **A benchmark suite** (writes/s for buffered and sync, restore time per
  million actions, snapshot pause) so these changes can be measured.

### 1.5 Concurrency

- **asyncio facade.** The proxy takes a `threading.RLock`, which blocks an
  event loop. An `AsyncPersistent` could run all writes on one dedicated
  writer thread and expose `await todo.add("milk")`.
- **Free-threaded Python** (3.13t/3.14t, no GIL). coopy already serializes
  writes with its own lock, so it should work, but the domain object's reads
  are no longer protected by the GIL. Add a free-threaded job to the CI matrix
  and document what readers may assume.

### 1.6 Tooling

- **ruff** for linting and formatting, run in CI and pre-commit.
- **Property-based tests with Hypothesis.** coopy's core promise is perfect
  for this: generate random sequences of method calls, snapshots and
  restarts, and assert that the restored state always equals the live state.
- **Coverage gate** in CI so it doesn't regress.
- **Dependabot** for the GitHub Actions versions.
- **Docs:** keep Sphinx (it already builds in CI) and add an API reference
  generated from the type hints.

### 1.7 Quick wins found while writing this

- The replication password is sent in plain text and checked with `!=`,
  which is not constant-time. Use `hmac.compare_digest`, and treat the
  password as a stopgap until the transport is encrypted (see 2.2).
- `linux_epoll.py` and `osx_kqueue.py` are empty. Delete them; the
  standard-library `selectors` module (or pyzmq) already picks the best
  mechanism per OS.

---

## Part 2 — Distribution

### 2.0 The key insight: coopy is already a replicated state machine

A *replicated state machine* is a deterministic program plus an ordered log
of inputs. Every replica that applies the same log in the same order ends up
in the same state. That is exactly coopy's design: the domain object is the
state machine, and the journal is the log.

So distribution reduces to one problem: **getting every node the same log in
the same order**, and deciding what happens when nodes fail or disagree.
Today one master decides the order and replicas follow. Everything below
changes who decides the order, and how.

### 2.1 Step 1: a transport interface

Replication is hard-wired to the `select`-based `CopyNet` in
`coopy/network/default_select.py`. Define a small interface so transports can
be swapped without touching the proxy:

```python
class Transport(Protocol):
    def publish(self, seq: int, action: Action) -> None: ...      # primary: live stream
    def serve_bootstrap(self, snapshot: Callable[[], tuple[int, bytes]]) -> None: ...
    def subscribe(self, apply: Callable[[int, Action], None],
                  load_snapshot: Callable[[int, bytes], None]) -> None: ...  # replica
    def close(self) -> None: ...
```

The important addition is the **sequence number**: every action gets a
monotonically increasing position in the log. Replicas track the last
position they applied, which makes gap detection, catch-up and failover
possible.

### 2.2 Step 2: a pyzmq transport

[pyzmq](https://pyzmq.readthedocs.io/) gives us message framing, reconnects
and many socket patterns for free. The current hand-written socket code
(partial reads, framing, client queues, authentication) is most of
`default_select.py`; with ZeroMQ it largely disappears.

The ZeroMQ Guide's
[**Clone pattern**](https://zguide.zeromq.org/docs/chapter5/) describes
almost exactly what coopy replication needs: reliable state replication from
one server to many clients. Mapped onto coopy:

```
                   primary
        ┌───────────────────────────┐
        │ domain object + journal   │
        │                           │
        │  PUB  ──── live actions (seq, action) ─────────► SUB   replica
        │                           │                         │
        │  ROUTER ◄── "snapshot from seq N?" ─────────── DEALER │
        │         ──── snapshot @ seq S + actions S..now ──►    │
        └───────────────────────────┘
```

1. A new replica **subscribes first**, buffering live actions.
2. It then asks the ROUTER socket for a snapshot, which comes back tagged
   with the sequence number it represents.
3. It loads the snapshot, drops buffered actions at or below that sequence
   number, and applies the rest. This is the same bootstrap F5/F13
   implemented, with sequence numbers making it simpler.
4. If it ever sees a gap in sequence numbers, it asks the ROUTER for the
   missing range.

Things to get right:

- **PUB/SUB drops messages** when a subscriber is slow and hits its
  high-water mark. Sequence numbers plus gap recovery (step 4) are mandatory,
  not optional.
- **CURVE security.** ZeroMQ's CURVE mechanism gives authenticated, encrypted
  connections with public keys. It replaces the plain-text password and keeps
  pickles away from unauthenticated peers.
- **Optional dependency.** pyzmq is a compiled package; ship it as
  `pip install coopy[zmq]` and keep the standard-library transport as the
  default.
- **Same transport, more topologies.** Once replication speaks ZeroMQ, IPC,
  TCP and in-process transports all work through the same code, which also
  makes multi-node tests easy to run in a single process.

### 2.3 Step 3: failover

With sequence numbers, a replica knows exactly how far behind it is, so it
can be promoted when the primary dies.

- **Primary/backup pair.** The Guide's
  [Binary Star pattern](https://zguide.zeromq.org/docs/chapter4/) pairs a
  primary with a hot backup that takes over when heartbeats stop.
- **Fencing with epochs.** The danger in any failover is *split brain*: two
  nodes both believing they are primary and accepting writes, so their logs
  diverge. Each promotion must bump an epoch number stored with every log
  entry, and nodes must reject writes from an older epoch. Binary Star alone
  does not fully prevent split brain during a network partition; a third
  voter, or the consensus approach in 2.4, does.

### 2.4 Step 4: multi-master

"Multi-master" can mean two different things, and the answer differs:

- **Any node accepts writes**, but all nodes still agree on one global order.
- **Nodes accept writes independently**, even when they can't talk to each
  other, and reconcile later.

| Approach | How writes are ordered | Fits coopy's model? | Main cost |
| --- | --- | --- | --- |
| **A. Consensus (Raft)** | A leader is elected; every node forwards writes to it; an entry is committed once a majority has stored it | Perfectly — Raft *is* a replicated log for state machines | Each write waits for a majority round trip; needs 3+ nodes; minority side of a partition can't write |
| **B. Partitioned single-writer** | Data is split into shards; each shard has its own log and its own primary | Yes, per shard | Calls touching two shards need coordination (two-phase commit or sagas) |
| **C. Optimistic order with rollback** | Each node applies writes immediately, ordered by hybrid logical clock; when an earlier-stamped write arrives late, roll back to a snapshot and replay in the corrected order | Yes, thanks to snapshots + replay | Users can see state "change its mind"; replay cost grows with how late messages arrive |
| **D. Commutative operations (CRDTs)** | Order doesn't matter because operations commute | Only for special data types | Breaks the "plain objects" promise; domain must be written as CRDTs |

**Recommendation:**

1. **Raft (A) is the natural "multi-master" for coopy.** Any node accepts a
   method call, forwards it to the leader, and returns once the call is
   committed and applied locally. Applications get one consistent order,
   automatic failover with no split brain, and no change to how domain
   classes are written. Reads can be served locally (fast, possibly slightly
   stale) or through the leader (up to date). Evaluate existing Python Raft
   libraries such as PySyncObj before writing our own; Raft is subtle to
   implement correctly.
2. **Sharding (B) is how to scale writes** beyond one leader once A works:
   one Raft group per shard.
3. **C and D are research.** C is the most interesting for offline use (see
   Part 3). D could appear as a small opt-in library of commutative types
   (counters, sets, last-writer-wins registers) for hot spots, not as the
   default model.

### 2.5 Prerequisites for any distributed mode

These matter as soon as two machines replay the same log:

- **Set iteration order differs between processes.** String hashing is
  randomized per process (`PYTHONHASHSEED`), so iterating a `set` of strings
  can produce a different order on each node. Domain code that depends on
  set order will silently diverge. Document this, and consider a validation
  warning or a replay-equivalence check across processes in tests.
- **A distributed clock.** `self._clock.now()` replays recorded wall-clock
  values, which is fine. But ordering across nodes (approach C) needs hybrid
  logical clocks, not wall clocks, because machine clocks drift.
- **Mixed versions.** During a rolling upgrade, nodes run different code. Log
  entries need a version, and nodes must refuse entries they can't apply
  (ties into 1.3 upcasters).
- **Safe serialization.** Pickle between machines in one trusted cluster
  with CURVE is acceptable; anything more open needs the safe serializer
  from 1.3.
- **Divergence detection.** Periodically hash the state on each node at the
  same log position and compare. It's cheap insurance against
  non-determinism bugs.

---

## Part 3 — Ambitious idea: decentralized coopy

> Every device keeps a full copy of the object, works offline, and syncs
> with any peer it can reach. No server.

This is the *local-first* model (apps like Figma's multiplayer, Automerge,
or git itself) applied to coopy's plain objects.

### Sketch

- **A log shaped like git.** Each action is content-addressed: its ID is the
  hash of its contents plus the IDs of the actions it was made after. The
  log becomes a Merkle DAG instead of a list. Any two peers can compare what
  they have by exchanging hashes, and history is tamper-evident.
- **Signed actions.** Each peer has a key pair (Ed25519) and signs its
  actions, so peers know who did what and can't forge each other's entries.
- **Discovery and sync over ZeroMQ.** Peers find each other on a local
  network with UDP beacons ([Zyre](https://github.com/zeromq/zyre) has a
  Python implementation, pyre) and exchange missing actions directly.
- **Deterministic order with rollback.** All peers sort the DAG the same way
  (topological order, ties broken by hybrid-clock timestamp, then hash). When
  a peer receives actions that sort earlier than ones it already applied, it
  restores the last snapshot before that point and replays — approach C from
  2.4. coopy's snapshot + replay machinery is exactly what this needs, which
  is what makes the idea plausible rather than fantasy.
- **Checkpoints by agreement.** The DAG can't grow forever. Peers agree on
  "everything before this hash is final", snapshot there, and prune.

### What it would take

| Prerequisite | Why |
| --- | --- |
| Safe serialization (1.3) | Pickle from arbitrary peers is remote code execution |
| Cheap snapshots (1.4) | Rollback happens often; it must not stall the app |
| Hybrid logical clocks (2.5) | Ordering across devices without trusting their clocks |
| Pluggable transport (2.1) | Sync over ZeroMQ, files, or anything else |
| Determinism checks (2.5) | Silent divergence is the main failure mode |

### Honest limits

- Users will occasionally see their own changes reordered after a sync, and
  operations that *conflict* (two people deleting the same item) resolve by
  the deterministic order, not by intent. Apps need to accept that.
- Protecting against peers that actively lie (Byzantine faults) is out of
  scope; signatures identify authors but don't stop a malicious peer from
  sending valid-but-hostile operations.
- This is research-grade work. It should start as a separate experimental
  package (for example `coopy-mesh`) built on the transport interface, not
  as a change to core coopy.

---

## Suggested sequencing

| Phase | Work | Depends on | Size |
| --- | --- | --- | --- |
| 1 | Quick wins (1.7), type hints on the public API + `py.typed`, ruff, Hypothesis replay test | — | S–M |
| 2 | Context manager, `pathlib`, exception hierarchy, primary/replica naming | 1 | M |
| 3 | Transport interface with sequence numbers (2.1); port `CopyNet` onto it | 1 | M |
| 4 | pyzmq transport with Clone-pattern bootstrap and CURVE (2.2) | 3 | M–L |
| 5 | Versioned actions, upcasters, pluggable serializer (1.3) | 1 | L |
| 6 | Group commit and fork-based snapshots (1.4) | — | M |
| 7 | Failover with epochs (2.3), then Raft multi-writer clusters (2.4 A) | 3, 4, 5 | XL |
| 8 | Decentralized prototype as a separate package (Part 3) | 4, 5, 6 | XL, research |

Phases 1–3 make coopy more pleasant and are low risk. Phase 4 is the first
step that is genuinely new. Phases 7 and 8 are where coopy would become a
distributed persistence system rather than a persistence library — worth
doing only once the single-node guarantees in ROADMAP.md are solid.

## Open questions

- Should coopy stay a small library, with distribution living in separate
  packages (`coopy-zmq`, `coopy-raft`, `coopy-mesh`), or grow into one
  package with extras?
- Is pyzmq the right foundation, or would asyncio streams plus a Raft
  library be simpler to maintain? pyzmq earns its place mainly through the
  Clone pattern, CURVE and transport flexibility.
- Which matters more to real users: multi-writer clusters (2.4 A) or
  offline-first sync (Part 3)? The two lead to quite different designs.
