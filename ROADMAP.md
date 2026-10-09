<!-- aiflow:roadmap -->
# coopy roadmap

coopy is a BSD-licensed Python object-prevalence library for developers who want to keep a domain model in memory and recover it across restarts without an ORM. The main journey is to wrap an object with `coopy.base.init_persistent_system`, call its methods, close it, and restore from local snapshots and transaction journals. Periodic snapshots and optional master/slave replication extend that journey, but both have correctness gaps described below.

Scope is the single Python library in this repository, not a monorepo or a hosted service. Preserve ordinary domain classes, the small proxy API, and Python 3.10+ support. Runtime code uses the standard library; setuptools builds distributions, pytest/pytest-cov support tests, and Sphinx sources live in `docs/`. `CoopyProxy` publishes actions to `DiskJournal` and optionally CopyNet; `SnapshotManager` stores the object graph, and `restore` replays actions. Storage is numbered pickle files, while CopyNet uses compressed pickle over TCP or Unix sockets. These require trusted data and peers. State must fit in memory, mutations must pass through proxy methods, and replay requires deterministic domain behavior; `_clock` only addresses time. Direct changes to exposed objects are not automatically journaled. Pyro appears only in old documentation, not as an implemented integration.

Evidence reviewed on 2026-10-09: `README.md` first, then implementation and tests under `coopy/` and `tests/`, `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, and documentation including the changelog, usage, clocks, snapshots, replication, and old planning notes. No applicable `AGENTS.md` was found. Repository root is `/Users/felipecruz/Projects/coopy`; branch is `main` at `d859e69af8c4fc131bbd6e26a7cc23c69cb2609d`. The initial working tree was clean. At final verification, an untracked `README.markdown` appeared concurrently; it was inspected and left untouched. Its prose is not evidence of implemented behavior, and its presence does not fix packaging from a clean checkout. Findings below describe committed code, not local feature changes; this task changes only this document and preserves the README.

History is non-shallow with 122 reachable commits. Review covered the latest 50, older capability-specific diffs, and rename-following README history. The only local tag is `0.4b`, matching its historical package manifest; subsequent manifests reached `0.4.6b`. Current code, README, and changelog declare `0.5.0`, but there is no local 0.5.0 tag or verified publication. CI defines testing on Python 3.10–3.14 for Linux/macOS and tag-triggered PyPI publishing; configuration is not evidence of successful runs or releases. Core persistence already exists in the initial import, so its original implementation provenance cannot be reconstructed. Old planning files only ask for a stable release and finished documentation. The proposed priority is therefore recoverable local persistence before wider replication use.

Checked items record verified implemented behavior. AIFlow also uses checks as request selections: clear the completed selections and select the desired planned items before copying an implementation request. Done timestamps record this audit date, not release dates.

## v0.5.0 — Establish the current persistence baseline

Current declared code baseline; release publication is unverified. Goal: identify what developers can use today and where correctness ends. Audit exit criterion: implemented paths have code/test evidence, and incomplete workflows remain explicitly partial. This baseline does not certify production readiness.

- [x] **F1 — Persist ordinary method calls across a clean restart.** The proxy records non-readonly, non-abort-decorated calls, returns domain results, and reconstructs state from an initial snapshot plus journal replay.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Details | `coopy/base.py`, `journal.py`, `restore.py`, and `fileutils.py` implement proxy dispatch, default reentrant locking, readonly exclusion, numbered journals, and restart replay. Original persistence code predates the available import; no original implementation commit is assigned. |
  | Validation | The focused run passed functional Wiki restart tests and unit checks for proxy dispatch, journals, and file rotation. This verifies ordinary clean restarts, not crash safety. |
  | Limitation | Successful abort-decorated writes are omitted; see F8. Writes after a later snapshot can be lost on restore; see F7. |
  | Limitation | Restore can continue after corruption or replay divergence; see F11. A returned mutation has no per-call fsync guarantee; see F12. |

- [x] **F2 — Replay recorded clock values and flag obvious clock misuse.** `_clock.now()`, `_clock.utcnow()`, and `_clock.today()` record values for ordered replay; initialization checks source for direct forbidden date/time calls.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Details | `coopy/foundation.py` provides recording/restoring clocks; `validation.py` checks inspectable methods. `coopy/tests/utils.py` supplies real and fixed clocks for domain tests. |
  | Commit | `d7324916d83622fef9f67bfaa5e8ac88c0b01a2c` — expands recorded clock values and ordered replay; `9ab444dd4ba4795dea201a203fa36867ef07ee90` — integrates method validation into initialization. |
  | Validation | Clock unit tests, multiple-clock-call restart, bad-system rejection, clock helpers, and source-unavailable validation all passed in the focused run. |
  | Limitation | Source-unavailable methods are skipped with a warning, and AST checks are not a general determinism guarantee; aliases, nested objects, randomness, and external side effects remain the application's responsibility. |

- [ ] **F3 — Recover reliably across manual and timed snapshots.** Snapshot serialization and locking exist, but checkpoint recovery is incomplete. Completion requires post-snapshot writes to survive restart and failed snapshots to preserve the previous usable checkpoint, as specified in F7 and F9.

  | Item | Content |
  | --- | --- |
  | Status | Partial |
  | Details | `coopy/snapshot.py` saves/loads snapshots and runs a background timer; `CoopyProxy.take_snapshot` locks writes and releases locks in finally blocks. Timer startup returns immediately and close stops it. Journals are not advanced at the checkpoint boundary, and snapshot files are written directly under their final names. |
  | Commit | `b14bd7d83b9a5913079f4b29c61d9e98b02c167d` — locks snapshot capture; `76279581872c5d3d768355e2f2126d09b8020730` — nonblocking timer startup, timer cleanup, and exception-safe lock release. |
  | Validation | Snapshot round-trip, proxy-lock, and nonblocking-timer tests passed. Separate temporary probes reproduced loss of a post-snapshot write and EOFError after a failed snapshot, despite an older good snapshot. |
  | Limitation | F7 addresses the journal boundary; F9 addresses incomplete snapshot publication. Existing snapshot tests do not exercise these failures. |

- [x] **F4 — Run the core library on modern Python without six.** The runtime uses Python 3 APIs and standard-library dependencies, with the package version centralized in `coopy/__init__.py`.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Details | `pyproject.toml` requires Python 3.10+ and declares test extras. The modernization removes six, uses unittest.mock in tests, delays file logging until initialization, and replaces deprecated UTC clock calls. CI build/publish configuration exists but has not been verified operationally here. |
  | Commit | `76279581872c5d3d768355e2f2126d09b8020730` — Python 3 modernization, version/packaging migration, and GitHub Actions workflow. |
  | Validation | 52 focused tests passed on Python 3.12.2 with DeprecationWarning treated as an error. Other Python versions and hosted CI were not run. |
  | Limitation | Packaging still references the renamed README; F6 repairs and validates the distribution path. |

- [ ] **F5 — Synchronize a new read-only slave with its master.** Transport and live action replay code exist, but a newly connected slave does not receive the master's initial state. Completion requires the bootstrap and ordered catch-up checks in F13.

  | Item | Content |
  | --- | --- |
  | Status | Partial |
  | Details | `coopy/network/default_select.py` contains password checking, broadcasts, exact-length packet reads, slave clock replay, and a proxy write guard. The call to CopyNetSnapshotThread is commented out in the accept loop, new clients are immediately marked ready, and select receives no writable sockets to drain bootstrap queues. |
  | Commit | `d9921b3a6e8e3bd1bd677097a44430d77bdd469d` — introduces the select-based transport; `76279581872c5d3d768355e2f2126d09b8020730` — Python 3 byte handling, slave construction, packet reads, and clock replay fixes. |
  | Validation | Packet serialization tests passed. Socket tests were read but not run; no successful end-to-end master/slave synchronization is claimed. |
  | Limitation | The full-state synchronization described in `docs/replication.rst` is not wired into the current master; see F13. Transport remains trusted-network-only and is not a durable replica log or automatic failover system. |

## v0.5.1 — Make installation and local recovery dependable

Planned corrective version, not a release claim. Goal: users can install the package and retain successful local changes through snapshots and clean restarts. Exit criterion: F6–F10 acceptance checks pass, with regression coverage for the three reproduced persistence failures and accurate executable documentation.

- [ ] **F6 — Build distributions with the actual README.** `pyproject.toml` points to `README.markdown`, absent from HEAD after its rename to `README.md`. An untracked replacement appeared during this audit; preserve and reconcile that work when fixing metadata, while preserving `README.md` content. Accept when sdist and wheel build, `twine check --strict` passes, both include the expected project description, and installation from the built artifacts can import coopy and complete a temporary-directory persistence round trip.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

- [ ] **F7 — Preserve every write after a checkpoint.** Snapshot numbering overtakes the still-open journal, while `last_log_files` only selects journals numbered after the latest snapshot. Establish an unambiguous checkpoint/replay boundary while holding the domain lock. Accept when write A → snapshot → write B → close → reopen restores both exactly once; cover repeated snapshots, writes after reopening, timer-triggered snapshots, and journal rotation with shared object references. Do not silently reinterpret existing files without compatibility tests.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

- [ ] **F8 — Journal successful abort-decorated calls.** `CoopyProxy.__getattr__` currently suppresses every `@abort_exception` action, including success. Suppress journaling only when the decorated call raises. Accept when a successful decorated mutation survives restart, a failing decorated call is omitted and its exception reaches the caller, and ordinary failing calls retain their existing journal behavior. Document that this decorator does not roll back in-memory mutations or external effects; add tests for readonly interaction.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

- [ ] **F9 — Keep the previous checkpoint usable when snapshot creation fails.** `SnapshotManager.take_snapshot` opens the final numbered file before serialization succeeds; recovery then selects that incomplete file. Publish a snapshot only after a complete successful write, keeping incomplete work out of snapshot discovery. Accept with injected serialization/write failures and interruption before publication: the previous checkpoint remains loadable, necessary journals remain available, and successful checkpoint publication still passes F7's restart cases. Depends on F7 for coordinated journal boundaries.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

- [ ] **F10 — Provide a working persistence and recovery guide.** `docs/usage.rst` and `docs/tutorial.rst` use obsolete init_system signatures/imports; clock and replication examples also disagree with code. Replace them with current `coopy.base.init_persistent_system` examples covering close/reopen, `_clock`, readonly methods, snapshots, and decorator semantics. Accept when maintained examples execute in temporary directories, the Sphinx documentation builds, and replication is explicitly marked incomplete until F13. Explain mutable-object escape paths, trusted pickle storage, replay side effects, and the current durability contract without changing README.md.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

## v0.6.0 — Expose recovery guarantees and complete slave bootstrap

Provisional later plan, not a scheduled release. Goal: callers can distinguish complete recovery from partial state and use replication with a defined synchronization boundary. Exit criterion: the selected recovery/durability contracts are documented and fault-tested, and a slave joining a populated master reaches matching state through concurrent updates.

- [ ] **F11 — Make incomplete recovery visible to callers.** `restore.py` logs several decoding/replay failures and continues, while EOFError is always treated as ordinary end-of-file. Provide an explicit strict recovery path that refuses to expose a usable proxy after detected corruption or divergence, plus an explicitly chosen salvage path reporting what was recovered and where it stopped. Accept fixtures for a truncated record, corrupt middle record, missing method, originally successful action now failing, and originally failing action now succeeding; preserve expected exceptions and identify legacy actions lacking outcome metadata. Depends on F7 and F9 so checkpoint defects do not masquerade as recovery policy.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

- [ ] **F12 — Offer an explicit synchronous durability contract.** `RotateFileWrapper.write` flushes user-space buffers, but normal action completion does not call fsync; its close method simply closes the file. Add an opt-in synchronous policy that acknowledges a journaled mutation only after the configured disk synchronization succeeds, retaining a documented buffered mode. Accept fault-injected write/flush/fsync failures with no false success, observable synchronization in synchronous mode, and restart checks across journal rotation. Clearly report that a persistence failure may leave memory changed; do not promise rollback. Depends on F7 and F9 for coherent checkpoint handling.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

- [ ] **F13 — Bootstrap slaves from a consistent state and ordered updates.** Wire snapshot transfer and catch-up into the master/slave lifecycle so a late joiner receives existing state before subsequent actions and is not exposed as synchronized early. Accept an integration test with a populated master, a new slave, concurrent writes during transfer, and recorded clock values: after catch-up, state matches with no missing or duplicate actions. Authentication rejection, fragmented packets, and interrupted bootstrap must leave the slave explicitly unsynchronized. This remains trusted-peer replication; automatic failover and durable slave restart are outside this item's scope.

  | Item | Content |
  | --- | --- |
  | Status | Planned |

## Validation record

Checks ran against a temporary copy of current source/tests using the existing repository virtual environment, without installs, services, or network calls. The README and starter hashes were recorded; the target was reread immediately before replacement. `make test` was not invoked because it first runs a destructive clean target. Its pytest step was adapted to exclude socket activity and repository cache writes:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/felipecruz/Projects/coopy/.venv/bin/python -m pytest --verbose -W error::DeprecationWarning -p no:cacheprovider --ignore=tests/unit/test_network_select.py -k 'not start_master and not master_accepts_writes and not start_slave'
```

Result: **52 passed, 3 deselected**, with the nine socket tests in the ignored module not collected. This is a focused run, not the full CI matrix or a coverage measurement; the old coverage table in `docs/tests.rst` was not treated as current evidence.

Additional temporary Python probes invoked the real library: creating `before`, taking a snapshot, then creating `after` restored only `before`; a successful abort-decorated counter increment restored 0 instead of 1; serializing an object whose `__reduce__` raises left a newer snapshot that made recovery raise EOFError. A `tomllib` metadata check in the temporary source copy confirmed the declared README path does not exist in that checkout; the later untracked replacement was not part of the check. These failures establish F7–F9 and F6; no fixes were made. Build/install checks remain unverified because the existing environment lacks setuptools, build, and twine; no dependencies were installed. Replication, crash/power-loss behavior, historical pickle compatibility, and published artifacts were not validated.

AIFlow validation used `'/Users/felipecruz/Projects/aiflow/build/AIflow.app/Contents/MacOS/MarkdownPreview' --check '/Users/felipecruz/Projects/coopy/ROADMAP.md'`: **0 errors, 2 warnings**. Both warnings recommend marking partial items with implementation commits Done. F3 and F5 deliberately retain Partial status and their provenance because the corresponding recovery/synchronization outcomes are incomplete; marking them Done would contradict the evidence.

Open decisions for v0.6.0: choose whether strict recovery becomes the default or stays opt-in, define how synchronous durability interacts with existing buffered behavior, and decide which historical pickle formats merit explicit migration support before making compatibility promises.
