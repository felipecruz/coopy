# Applying coopy in 2026

Where coopy fits today, where it could fit once the plans in
[FUTURE.md](FUTURE.md) land. Section 2 covers data science, experimentation
and machine learning; section 3 covers everything else: games, ledgers,
bookings, bots, edge devices, developer tooling and more.

Ideas are labelled by what they depend on:

- **Today**: works with the current release (strict recovery, sync durability,
  `coopy.control`, `AsyncPersistent`, JSON serializer, HMAC integrity,
  experimental replication).
- **Next**: needs an item from FUTURE.md Part 1 or 2 (transport interface,
  pyzmq, failover).
- **Ambitious**: needs FUTURE.md Part 2.4 or Part 3 (multi-master,
  decentralized log).

---

## 1. What coopy is good at, in one paragraph

coopy keeps a Python object graph in memory and writes every state-changing
method call to a journal. Recovery is "load the latest snapshot, replay the
calls after it". That gives you three things most storage layers don't:

1. **Memory-speed reads** over plain Python objects: no queries, no ORM.
2. **A complete, ordered history of intent**: not "row 17 changed", but
   `record_metric(run_id, "val_loss", 0.231, step=1200)`.
3. **Deterministic replay**: the same calls in the same order rebuild the
   same state, which is also the basis for replication.

The constraints are the other side of the same coin: state must fit in RAM,
methods must be deterministic, and arguments must be serializable.

### The pattern that makes coopy work for ML

> **Compute outside, journal the decision.**

Anything expensive, random or non-deterministic (training a network, a GPU
kernel, an LLM call, a network request) runs *outside* the domain object.
Only its **result** goes in as a method argument. Replay never retrains a
model or calls an API; it just re-applies recorded outcomes.

```python
# outside coopy: slow, random, GPU
metrics = train_one_epoch(model, loader, seed=seed)
path, digest = save_checkpoint(model)          # weights go to disk/object store

# inside coopy: fast, deterministic, journaled
lab.finish_epoch(run_id, epoch, metrics, checkpoint=path, sha256=digest)
```

Large binary data (weights, datasets, embeddings matrices, images) is stored
elsewhere and referenced by path and hash. coopy holds the **metadata, the
decisions and the lineage**.

---

## 2. Data science, experiments and ML

### 2.1 Experiment tracker you own (Today)

A self-hosted alternative to a tracking server for a team or a single
researcher: runs, parameters, metrics, tags, artifacts by reference.

```python
from dataclasses import dataclass, field
from datetime import datetime

from coopy.decorators import readonly
from coopy.foundation import RecordClock


@dataclass
class Run:
    params: dict[str, float | int | str]
    started: datetime
    metrics: dict[str, list[tuple[int, float]]] = field(default_factory=dict)


class Lab:
    _clock: RecordClock

    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}

    def start_run(self, run_id: str, params: dict[str, float | int | str]) -> None:
        self.runs[run_id] = Run(params=params, started=self._clock.now())

    def log_metric(self, run_id: str, name: str, value: float, step: int) -> None:
        self.runs[run_id].metrics.setdefault(name, []).append((step, value))

    @readonly
    def best(self, metric: str, n: int = 5) -> list[str]:
        ...
```

Why coopy: queries such as "best 5 runs by `val_loss` where `lr < 1e-3`" are
plain Python over in-memory dicts, so they stay fast. The journal is an audit
trail of every run. Use `durability="sync"` for metrics you can't lose, or
the default buffered mode with group commit for high-frequency logging.

Limits: one writer process per data directory. Many training jobs should
send metrics to a small service that owns the coopy object (see 2.6), not
open the directory themselves.

### 2.2 Hyperparameter search coordinator (Today, then Next)

The state of a study (trials, their parameters, status, results, pruning
decisions) is small, structured and changes through clear commands:
`ask()`, `tell(trial, value)`, `prune(trial)`.

- **Today:** a single coordinator process owns the study; workers ask for
  trials over HTTP or a queue. A crash loses nothing: reopen and the study
  continues with the same trial history.
- **Determinism catch:** samplers use randomness. Draw random numbers
  *outside* the domain and pass them into `ask(proposal)`, or seed the sampler
  from journaled data (trial count + study seed) so replay reproduces the same
  suggestions.
- **Next:** replicas of the study serve dashboards and read-only analysis
  without touching the coordinator.

### 2.3 Online and incremental models (Today)

Some models *are* small state updated by events, which is exactly what
coopy journals:

- **Multi-armed and contextual bandits** for A/B/n tests, recommendations or
  pricing: `record_reward(arm, reward)`. The journal is the experiment log;
  replay reproduces the posterior exactly.
- **Online linear models** (SGD logistic regression, recursive least squares)
  where each `update(x, y)` is a journaled call.
- **Streaming sketches and statistics**: counts, HyperLogLog, t-digest
  quantiles, exponential moving averages, drift detectors.
- **Feature aggregates** for online serving: per-user counters and rolling
  windows that a model reads at inference time.

Floating-point note: replaying the same operations in the same order on the
same platform gives identical floats. Pin library versions; a NumPy or BLAS
upgrade that changes summation order can change replayed results. Strict
recovery only notices when a call that succeeded now raises (or the reverse);
it does not compare values, so keep a checksum of important state if you
need to detect silent drift.

### 2.4 Data labelling and active learning (Today)

A labelling queue is a textbook prevalent system: items, assignments,
labels, disagreements, reviewer decisions. Active learning adds a loop:

1. Model scores unlabelled items (outside coopy).
2. `queue.prioritize(scores_version, ranking)` journals the new order.
3. Annotators call `queue.label(item_id, label, annotator)`.
4. Retraining reads a consistent snapshot of labels via a `@readonly` export.

You get who-labelled-what-when for free, which matters for dataset audits and
inter-annotator agreement.

### 2.5 Model registry and evaluation leaderboard (Today)

Models are referenced by artifact URI and hash; coopy stores versions,
stages (`staging`, `production`, `archived`), evaluation results per dataset
version, and approvals. Promotions become journaled commands:
`promote(model, "production", approved_by=...)`, so "what was in production
on 3 March?" is a replay question with an exact answer.

### 2.6 Training-run control plane (Today)

Long training runs on preemptible GPUs need durable, tiny state: current
epoch, best checkpoint, learning-rate schedule position, early-stopping
counters, data-loader cursor. Store that in a coopy object owned by the
launcher; weights stay in checkpoint files. After preemption, reopen coopy
and you know exactly which checkpoint and data offset to resume from.

### 2.7 Neural networks: what fits and what doesn't

| Fits well | Does not fit |
| --- | --- |
| Run metadata, metrics, configs, lineage | Model weights, optimizer state tensors |
| Checkpoint pointers and hashes | Datasets and embedding matrices |
| Curriculum and schedule state | Anything recomputed by a GPU during replay |
| Small heads updated online (bandit, calibrator) | Large models fine-tuned in place |
| Evaluation results per model × dataset | Raw prediction logs at high volume |

Rule of thumb: if it fits in a few GB of Python objects and changes through
meaningful commands, coopy is a good home. If it is a tensor, store a
reference.

### 2.8 Notebooks and analysis sessions (Today)

Notebook kernels die and lose state. A coopy object can hold the curated
results of an analysis (cleaned summaries, decisions, annotations, chosen
thresholds), so restarting the kernel and reopening the system restores them.
Keep domain classes in a `.py` module, not in a notebook cell: classes defined
in `__main__` can't be loaded by a later process.

### 2.9 Simulations and agent-based models (Today)

Agent-based simulations, games and digital twins are deterministic state
machines driven by events. Journaling the events makes every run
reproducible and lets you rewind: restore an earlier snapshot, then replay
part of the journal to inspect a moment, or branch with different inputs.
Seed every random generator from journaled arguments.

### 2.10 LLM agents and tool-using assistants (Today)

A 2026-shaped use: the long-lived memory and task state of an agent.

- Conversation summaries, facts the agent has learned, task lists, tool-call
  results and plans are small, structured and append-heavy.
- The LLM call happens outside; only its *result* is journaled
  (`agent.remember(fact, source=message_id)`), so replay is free and exact.
- The journal doubles as an audit log of every action an agent took, which
  helps when debugging agent behavior or answering "why did it do that?".
- `AsyncPersistent` fits async agent frameworks: domain calls are awaited and
  processed in order by one writer.
- Embeddings: store vectors in a vector index; keep IDs, metadata and the
  index version in coopy.

---

## 3. Beyond data science

The same rule applies everywhere: **compute outside, journal the decision**.
An HTTP call, a payment provider response or a sensor reading happens
outside the domain object; the result is passed in as an argument.

### 3.1 Internal tools and back offices (Today)

Admin panels, CRMs for a small team, onboarding checklists, asset inventories.
The data is small, the rules are the complicated part, and nobody wants to
run a database for them. Domain classes hold the rules; every change is a
named command (`assign_laptop(employee, serial)`) with a timestamp, which
answers "who changed this and when?" without extra audit tables.

### 3.2 Games (Today)

- **Turn-based and casual game servers**: lobbies, matches, inventories,
  leaderboards live in memory; a crash or deploy loses nothing.
- **Replays for free**: the journal of a match *is* its replay file. Restore
  the snapshot from the start of the match and replay moves at any speed.
- **Disputes and anti-cheat**: every move is recorded in order with its
  recorded time, so contested results can be re-run exactly.
- **MUDs and persistent worlds**: the classic object-prevalence use case;
  the world is one object graph that never has to be mapped to tables.

Keep random rolls outside the domain (or pass a seed in) so replay produces
the same dice.

### 3.3 Feature flags and configuration services (Today)

Tiny, read-heavy state with a strong need for history. Reads are attribute
access, so a flag check costs microseconds. The journal records every
change with who made it; point-in-time restore (ROADMAP F31) will answer
"what was the configuration during last night's incident?". Replicas (4.6)
can bring flags next to every service.

### 3.4 Workflows, approvals and case management (Today)

Purchase approvals, support tickets, document review, hiring pipelines,
insurance claims. Each is a state machine where transitions are commands
(`approve(request_id, by=...)`) and the rules ("two approvals above 10k")
are plain Python in the domain class. The journal is the audit trail that
compliance usually asks for separately.

### 3.5 Ledgers, wallets and quotas (Today)

Loyalty points, in-game currencies, prepaid credits, API quotas, the books
of a small association. Methods check invariants under coopy's lock (no
negative balances, no double spending) and `durability="sync"` acknowledges
a transfer only after it is on disk. HMAC integrity (`secret=`) detects
tampering with the files.

Not a fit for regulated banking: there is no replicated durability yet, and
real money needs audited infrastructure.

### 3.6 Bookings, reservations and inventory (Today)

Event tickets, meeting rooms, restaurant tables, stock for a small shop.
Overselling is a race condition; in coopy every reservation runs one at a
time through the proxy lock, so the check "seats left > 0" and the booking
happen atomically without database transactions or row locks. Payment and
email happen outside; the domain records `confirm(booking_id, payment_ref)`.

### 3.7 Backends for collaborative apps (Today)

Kanban boards, wikis (the docs use a wiki as the tutorial example), small
CMSs, comment threads, polls. With `AsyncPersistent`, an async web framework
(FastAPI, Starlette, aiohttp) can await domain calls from WebSocket handlers
while one writer keeps them ordered. Live updates to browsers can be sent
after each successful call.

### 3.8 Edge, IoT and embedded Linux (Today)

Raspberry Pi gateways, home-automation hubs, kiosks, point-of-sale terminals,
lab instruments. They need durable local state but shouldn't run a database
server. coopy is pure Python, keeps reads in memory, and `durability="sync"`
survives power cuts within the limits of the storage device. Sensor readings
are passed in as arguments; aggregates and device state live in the domain.

Mind SD-card wear on very high write rates: buffer readings and journal
summaries rather than every sample.

### 3.9 Desktop and command-line apps (Today)

Personal finance trackers, note-taking tools, todo apps, reading lists,
local-first utilities. State is a Python object instead of a hand-rolled
JSON file, and saves are automatic and crash-safe. The journal also makes
**undo history** natural: rebuild the state without the last N actions.
That needs point-in-time restore (ROADMAP F31); until then, take a snapshot
before risky operations.

### 3.10 Bots and automations (Today)

Discord, Slack and Telegram bots, home-server automations, CI helpers,
scheduled scrapers. Bots restart often (deploys, crashes, host reboots);
with coopy their subscriptions, reminders, counters and conversation state
come back exactly. The journal shows what the bot did and why.

### 3.11 Developer and platform tooling (Today)

- **Job schedulers and cron state**: last run, next run, retries, leases.
- **Service catalogs and deployment registries**: what version runs where,
  who deployed it, rollbacks as commands.
- **Rate limiters and lease managers**: counters and expiries checked in
  memory under one lock.
- **Mock servers and test doubles** that keep state across restarts during
  long integration test runs.

### 3.12 Record–replay debugging and teaching (Today)

- **Bug reports with a journal attached**: a user ships the data directory,
  you replay it locally and step through the exact sequence of calls that
  led to the bug (trusted data only: journals contain pickles unless you use
  the JSON serializer).
- **Deterministic fixtures**: build a test state once, snapshot it, and
  start every test from it.
- **Teaching event sourcing and CQRS**: coopy shows command journaling,
  snapshots, replay, determinism and upcasting in a few hundred lines of
  Python, without Kafka or a database.

### 3.13 Summary

| Application | Why coopy fits |
| --- | --- |
| Internal tools and admin back offices | Small data, complex rules, no DBA |
| Game servers, replays, persistent worlds | In-memory state, event replay, deterministic rules |
| Feature flags and configuration services | Tiny state, read-heavy, full change history |
| Workflow and approval engines | State machines with an audit requirement |
| Ledgers, wallets, quotas | Invariants under one lock, sync durability, tamper detection |
| Bookings and inventory | No overselling without database transactions |
| Collaborative app backends | Async writer, in-memory reads for live views |
| IoT edge gateways and kiosks | Local durable state without a database server |
| Desktop and CLI apps | Crash-safe saves, undo from the journal |
| Bots and automations | Long-lived state, restart safety |
| Developer and platform tooling | Leases, schedules and registries with history |
| Record–replay debugging, teaching | The journal reproduces the exact sequence |
| Prototypes that may become products | Start without a schema; journal keeps history |

Poor fits: data larger than memory, many independent writer processes on
one directory, ad-hoc SQL analytics by other teams, full-text search over
large corpora, and anything that needs cross-language access to the storage
format (the JSON serializer helps, but the journal is still a coopy format).

---

## 4. With the distributed ideas from FUTURE.md

### 4.1 Read replicas for inference and dashboards (Next)

Primary/replica replication (experimental today; FUTURE.md 2.1–2.3 make it
robust with a transport interface, pyzmq and failover) maps cleanly onto
ML serving:

- The **primary** owns the feature store, bandit state or model registry and
  accepts updates.
- **Replicas** sit next to inference servers and answer reads from local
  memory: online features, the current production model pointer, flag values.
- A pyzmq PUB/SUB fan-out (FUTURE.md 2.2, Clone pattern) lets many replicas
  follow one primary with sequence numbers to detect gaps.

### 4.2 A highly available experiment coordinator (Next)

Hyperparameter studies and labelling queues are coordination state. With
Binary Star failover (FUTURE.md 2.3) or Raft (2.4), a standby takes over when
the coordinator dies. Workers keep asking for trials, and no trial is issued
twice, because ordering is decided by one leader at a time.

### 4.3 Sharded state for many independent experiments (Ambitious)

FUTURE.md 2.4 compares Raft, sharding, optimistic rollback and CRDTs.
Experiments are naturally independent, so **sharding by study or project**
is the cheapest form of multi-master: each shard is a normal coopy system
with its own leader, and a thin router directs calls. Cross-shard queries
(a global leaderboard) are answered by replicas that subscribe to all shards.

### 4.4 Federated and collaborative research logs (Ambitious)

FUTURE.md Part 3 sketches a decentralized coopy: a Merkle DAG of signed
actions, peers discovered with Zyre, deterministic ordering with rollback.
For science this suggests:

- **Federated learning coordination**: sites keep data local and journal
  only round metadata and aggregated-update hashes; each site has a verifiable
  copy of the round history.
- **Multi-lab experiment logs**: every lab signs its runs (Ed25519); the
  shared DAG is a tamper-evident, append-only record of who ran what. That
  helps with reproducibility and provenance.
- **Offline-first field data collection** (ecology, clinical sites, edge
  devices): peers sync when connected and merge by deterministic order.

Honest limits (from FUTURE.md): merging divergent histories needs
commutative operations or rollback, and pickle is not safe between parties
who don't trust each other, so these ideas depend on a safe serializer
(the JSON serializer is the first step).

### 4.5 Configuration and flags at the edge (Next)

A primary owns feature flags, pricing tables or routing rules; replicas run
inside every service or region and answer reads from local memory. The
pyzmq Clone pattern (FUTURE.md 2.2) is designed exactly for this:
a snapshot on join, then a stream of numbered updates.

### 4.6 Sharded game worlds and tenants (Ambitious)

Game zones, chat rooms, or customers of a multi-tenant SaaS are naturally
independent. Sharding (FUTURE.md 2.4) gives each its own coopy system and
leader; a router sends calls to the right shard, and moving a tenant is a
snapshot transfer.

### 4.7 Local-first and offline apps (Ambitious)

Field-service apps, note-taking across laptops, point-of-sale terminals that
keep selling when the network is down. The decentralized log in FUTURE.md
Part 3 (signed actions in a Merkle DAG, peers discovered with Zyre) lets
devices work offline and sync later. This works when operations commute
(adding notes, recording sales); conflicting edits need deterministic
ordering with rollback or CRDT-style operations.

### 4.8 Reproducibility as a feature

Across all of these, the journal plus deterministic replay gives something
the ML community keeps asking for: **exact reconstruction of the state
behind any result**. Combined with HMAC integrity (detects tampered journals
and snapshots) and, later, signed actions, a coopy log can serve as evidence
for "this model was selected using these evaluations, made at these times,
by these people".

---

## 5. Practical checklist

1. Put domain classes in an importable module and annotate them; the proxy
   keeps their types (see the README's "Type hints" section).
2. Keep random numbers, I/O, network calls, payments, GPU work and LLM
   calls outside domain methods; pass results in as arguments. Use `self._clock` for time.
3. Store tensors and files elsewhere; keep URIs and SHA-256 hashes in coopy.
4. Pick durability per system: `sync` for registries and ledgers, buffered
   plus group commit for high-rate metrics.
5. Take snapshots on a schedule so replay stays short; prune old files with
   your own retention policy (coopy does not prune).
6. Pin numeric library versions if replay involves floating-point math.
7. Use `secret=` (HMAC) when journals move between machines or storage you
   don't fully control, and the JSON serializer when data must outlive
   class renames or be read by other tools.
8. Use one writer process per data directory; put a small service in front if
   many jobs need to write.

---

## 6. Ideas worth prototyping first

Ranked by value for the effort, using only what exists today:

1. **`coopy-lab`**: a minimal experiment tracker (2.1) with a CLI and a
   read-only web view. It's a showcase for typed domains and fast queries.
2. **Bandit service** (2.3): FastAPI + `AsyncPersistent` + Thompson sampling,
   with an example of exact replay of every decision.
3. **Agent memory** (2.10): a drop-in persistent memory for an LLM agent
   framework, with the journal as an audit log.
4. **Study coordinator** (2.2) once the transport interface lands, as the
   first real user of replication and failover.

Outside data science:

5. **Flag service** (3.3): a tiny feature-flag server with history and an
   admin page, the clearest demo of read speed plus audit trail.
6. **No-oversell booking demo** (3.6): concurrent buyers hammering a
   ticket sale, showing the lock keeps inventory exact without a database.
7. **Bot template** (3.10): a Discord/Slack bot whose state survives
   restarts, with the journal as its activity log.
8. **Bug replay kit** (3.12): a helper that packages a data directory and
   replays it under a debugger.
