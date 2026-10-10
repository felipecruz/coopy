<!-- aiflow:roadmap -->
# coopy roadmap

coopy is a BSD-licensed Python object-prevalence library for developers who want to keep a domain model in memory and recover it across restarts without an ORM. The main journey is to wrap an object with `coopy.base.init_persistent_system`, call its methods, close it, and restore from local snapshots and transaction journals. Periodic snapshots and optional master/slave replication extend that journey, but both have correctness gaps described below.

Scope is the single Python library in this repository, not a monorepo or a hosted service. Preserve ordinary domain classes, the small proxy API, and Python 3.10+ support. Runtime code uses the standard library; setuptools builds distributions, pytest/pytest-cov support tests, and Sphinx sources live in `docs/`. `CoopyProxy` publishes actions to `DiskJournal` and optionally CopyNet; `SnapshotManager` stores the object graph, and `restore` replays actions. Storage is numbered pickle files, while CopyNet uses compressed pickle over TCP or Unix sockets. These require trusted data and peers. State must fit in memory, mutations must pass through proxy methods, and replay requires deterministic domain behavior; `_clock` only addresses time. Direct changes to exposed objects are not automatically journaled. Pyro appears only in old documentation, not as an implemented integration.

Evidence reviewed on 2026-10-09: `README.md` first, then implementation and tests under `coopy/` and `tests/`, `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, and documentation including the changelog, usage, clocks, snapshots, replication, and old planning notes. No applicable `AGENTS.md` was found. Repository root is `/Users/felipecruz/Projects/coopy`; branch is `main` at `d859e69af8c4fc131bbd6e26a7cc23c69cb2609d`. The initial working tree was clean. At final verification, an untracked `README.markdown` appeared concurrently; it was inspected and left untouched. Its prose is not evidence of implemented behavior, and its presence does not fix packaging from a clean checkout. Findings below describe committed code, not local feature changes; this task changes only this document and preserves the README.

History is non-shallow with 122 reachable commits. Review covered the latest 50, older capability-specific diffs, and rename-following README history. The only local tag is `0.4b`, matching its historical package manifest; subsequent manifests reached `0.4.6b`. Current code, README, and changelog declare `0.5.0`, but there is no local 0.5.0 tag or verified publication. CI defines testing on Python 3.10–3.14 for Linux/macOS and tag-triggered PyPI publishing; configuration is not evidence of successful runs or releases. Core persistence already exists in the initial import, so its original implementation provenance cannot be reconstructed. Old planning files only ask for a stable release and finished documentation. The proposed priority is therefore recoverable local persistence before wider replication use.

**Release plan (updated 2026-10-10).** PyPI's latest release is still 0.3.1; `0.4b` exists only as a git tag, and 0.5.0 was declared in code but never tagged or published. The next release is **0.6.0**. It ships everything already implemented below (F1–F21) together with the release blockers F22–F25. Development milestones that were numbered v0.5.1, v0.6.0 and v0.7.0 while that work was planned are kept as subsections of the 0.6.0 release, so their history and evidence stay intact. Migrations and operational tooling follow in v0.7.0, and transactional rollback in v0.8.0. Distribution and decentralization stay in [FUTURE.md](FUTURE.md) Parts 2 and 3.

Checked items record verified implemented behavior. AIFlow also uses checks as request selections: clear the completed selections and select the desired planned items before copying an implementation request. Done timestamps record this audit date, not release dates.

## v0.5.0 — Establish the current persistence baseline

Declared in code but never tagged or published; this baseline ships as part of the 0.6.0 release. Goal: identify what developers can use today and where correctness ends. Audit exit criterion: implemented paths have code/test evidence, and incomplete workflows remain explicitly partial. This baseline does not certify production readiness.

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

- [x] **F3 — Recover reliably across manual and timed snapshots.** Post-snapshot writes survive restart, and failed snapshots retain the previous usable checkpoint, covering the recovery scenarios specified in F7 and F9.
  Complexity assessment before implementation: L; clear requirements across roughly seven code/test files in snapshot publication, journal rotation, and recovery. Historical broken checkpoint boundaries cannot be inferred safely; retain existing file interpretation and test legacy streams.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | L |
  | Details | Atomic temporary-file publication advances journals under the domain lock before exposing a checkpoint. Reopening creates a fresh journal; rotation occurs between complete records. Timer failures are logged and retried. |
  | Commit | `72ed79bba8621ed6a367b73b3b38c9d06f3831c2` — implements F3 recovery; prior snapshot groundwork: `b14bd7d83b9a5913079f4b29c61d9e98b02c167d`, `76279581872c5d3d768355e2f2126d09b8020730`.; `b9689fa636ebe856063fbed77c24c4e089aeb457` |
  | Validation | 62 persistence/core tests passed with DeprecationWarning as error; includes repeated/reopened/timed checkpoints, serialization/write/fsync/rotation/rename failures, process exit before publication, large-record rotation with aliases, and legacy protocol-2 streams. |
  | Limitation | Existing files with ambiguous post-snapshot writes in earlier journals cannot be repaired automatically; historical format interpretation is unchanged. |
  | Limitation | Power-loss durability, corruption recovery, and mutations bypassing the proxy lock remain outside this guarantee. Interrupted snapshots can leave ignored temporary files. |
  | Next step | Implement the explicit recovery and durability policies tracked in F11 and F12. |

- [x] **F4 — Run the core library on modern Python without six.** The runtime uses Python 3 APIs and standard-library dependencies, with the package version centralized in `coopy/__init__.py`.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Details | `pyproject.toml` requires Python 3.10+ and declares test extras. The modernization removes six, uses unittest.mock in tests, delays file logging until initialization, and replaces deprecated UTC clock calls. CI build/publish configuration exists but has not been verified operationally here. |
  | Commit | `76279581872c5d3d768355e2f2126d09b8020730` — Python 3 modernization, version/packaging migration, and GitHub Actions workflow. |
  | Validation | 52 focused tests passed on Python 3.12.2 with DeprecationWarning treated as an error. Other Python versions and hosted CI were not run. |
  | Limitation | Packaging still references the renamed README; F6 repairs and validates the distribution path. |

- [x] **F5 — Synchronize a new read-only slave with its master.** A late joiner receives the master's consistent state and ordered catch-up before becoming readable, covering the bootstrap scenarios specified in F13.
  Complexity assessment before implementation: L; clear requirements across roughly six files in proxy locking, transport, synchronization state, tests, and documentation. Synchronization means the snapshot and actions preceding an explicit catch-up marker have been applied; subsequent updates remain asynchronous.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | L |
  | Details | Snapshot capture shares the mutation lock; nonblocking socket queues preserve snapshot/action order. Bootstrap stays private until a ready marker. Reads and snapshots reject unsynchronized replicas; receiver failures clear readiness. |
  | Commit | `194b6b4b8366c5be40abf01e2d8f7873ddfc749a` — implements F5 bootstrap and catch-up; prior transport groundwork: `d9921b3a6e8e3bd1bd677097a44430d77bdd469d`, `76279581872c5d3d768355e2f2126d09b8020730`.; `b9689fa636ebe856063fbed77c24c4e089aeb457` |
  | Validation | Full suite: 83 passed on Python 3.12 with DeprecationWarning as error, including populated-master concurrent catch-up, live replay, recorded clocks, readonly guards, fragmented authentication/packets, rejection, interrupted bootstrap, replay divergence, and TCP/Unix shutdown. |
  | Limitation | Length-prefixed authentication and the ready marker require upgrading master and slaves together; old peers are incompatible. |
  | Limitation | Slow-slave queues are unbounded in memory; snapshot serialization still pauses master mutations. |
  | Limitation | Trusted-peer replication only; durable slave restart, automatic reconnect/failover, and synchronous acknowledgments are outside scope. Successful abort-decorated calls remain unpublished pending F8. |
  | Next step | Bound pending replication bytes per slave and disconnect clients exceeding the configured limit. |
  | Next step | Run the supported Python and operating-system CI matrix; this job validated local Python 3.12 only. |

## v0.6.0 — First release since 0.3.1

Next release. It contains the persistence baseline above, the implemented milestones below (F6–F21), and the open release blockers F22–F25. Goal: a published, installable package whose storage format, single-writer rule and migration story are explicit before users accumulate data. Exit criterion: F22–F25 acceptance checks pass, the full hosted CI matrix is green on the release commit, and the `v0.6.0` tag publishes to PyPI through the trusted-publishing job.

### Implemented: installation and local recovery (planned as v0.5.1)

Originally a planned corrective version. Goal: users can install the package and retain successful local changes through snapshots and clean restarts. Exit criterion: F6–F10 acceptance checks pass, with regression coverage for the three reproduced persistence failures and accurate executable documentation.

- [x] **F6 — Build distributions with the actual README.** At the original audit, `pyproject.toml` pointed to `README.markdown`, absent from HEAD after its rename to `README.md`. An untracked replacement appeared during that audit; preserve and reconcile that work when fixing metadata, while preserving `README.md` content. Accept when sdist and wheel build, `twine check --strict` passes, both include the expected project description, and installation from the built artifacts can import coopy and complete a temporary-directory persistence round trip.
  Complexity assessment before implementation: M; clear acceptance criteria across two implementation/tracking files, plus job notes; distribution validation and existing CI integration are the affected components. This job strengthens the installed-artifact round trip to restore in a fresh Python process. The stale metadata and replacement README were already reconciled in `986fecea236ea415207c1eddc0b9b1218f6f97b4`; preserve the current README verbatim and validate that result. No unresolved specification ambiguity.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Preserved the reconciled README.md and correct metadata path. Existing CI validates both artifact descriptions and installs each into a fresh environment; the round trip now writes a checkpoint and later journal entry, closes, exits, and restores both in a separate isolated Python process. |
  | Commit | `e6b0beb5afb3af651682e64b80f0d3b1ccc44204` — implements F6 process-restart validation; `ed54c62fae85316b848df09f871ee6e46635979a` — prior artifact validation and CI; `986fecea236ea415207c1eddc0b9b1218f6f97b4` — prior README reconciliation and metadata fix; `b4ac94cd052223008bdfa803e7d3b07841598087` — prior tracking only.; `cdf26573176589e166d949b2532314f9d9b2882c` |
  | Validation | Tracked-source export plus this script change: isolated sdist/wheel builds and strict twine checks passed; both descriptions match README.md and sdist README bytes match. Both fresh installs imported from site-packages and restored both writes after process exit. Python 3.12.2/macOS; README SHA-256 unchanged. git diff --check and AIFlow validation passed. |
  | Limitation | Hosted CI and other Python/OS combinations were not executed locally; the sdist installation check downloads build requirements. |
  | Next step | Run the updated hosted CI workflow to verify the Python 3.13/Linux distribution job. |

- [x] **F7 — Preserve every write after a checkpoint.** Snapshot numbering overtakes the still-open journal, while `last_log_files` only selects journals numbered after the latest snapshot. Establish an unambiguous checkpoint/replay boundary while holding the domain lock. Accept when write A → snapshot → write B → close → reopen restores both exactly once; cover repeated snapshots, writes after reopening, timer-triggered snapshots, and journal rotation with shared object references. Do not silently reinterpret existing files without compatibility tests.
  Complexity assessment before implementation: M; clear acceptance criteria across recovery tests, snapshot documentation, and roadmap tracking (three files, plus job notes). F3 already implemented the runtime boundary; this job adds concurrent-boundary and legacy-selection regression coverage. Historical files cannot reveal ambiguous post-checkpoint writes in earlier journals; preserve their interpretation.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Retained F3's domain-locked journal rotation before checkpoint publication and fresh journal on reopen. Added six regression cases for concurrent writes during manual/timed checkpoint rotation and publication, plus legacy journal selection and independent per-file memos. Documented the boundary without changing storage interpretation. |
  | Commit | `f9e3375dba4251d30ec4fe1063a99df6be4de0c8` — implements F7 regression coverage and boundary documentation; `72ed79bba8621ed6a367b73b3b38c9d06f3831c2` — prior F3 runtime checkpoint fix and recovery tests.; `83d80df015ed5ed3d300d2e2318234d4916f61d5` |
  | Validation | All 89 tests passed on Python 3.12.2/macOS with DeprecationWarning as error, including 16 checkpoint tests covering repeated/reopened/timed snapshots, concurrent writes, large-record rotation with aliases, failures, and legacy protocol-2 streams. Full suite required local socket access. AIFlow roadmap check and git diff --check passed. |
  | Limitation | Historical post-snapshot tails in journals at or below the checkpoint number cannot be inferred safely; those files retain their existing replay interpretation. |
  | Limitation | Aliases within records survive rotation; object identity across journal files or between snapshot state and later arguments is not guaranteed. |
  | Limitation | Power-loss durability and mutations bypassing the proxy lock remain outside the checkpoint guarantee; other Python/OS combinations were not run locally. |
  | Next step | Run the supported Python and operating-system CI matrix. |

- [x] **F8 — Journal successful abort-decorated calls.** `CoopyProxy.__getattr__` currently suppresses every `@abort_exception` action, including success. Suppress journaling only when the decorated call raises. Accept when a successful decorated mutation survives restart, a failing decorated call is omitted and its exception reaches the caller, and ordinary failing calls retain their existing journal behavior. Document that this decorator does not roll back in-memory mutations or external effects; add tests for readonly interaction.
  Complexity assessment before implementation: M; clear requirements across about seven implementation files in proxy dispatch, decorator documentation, and unit/restart tests, plus roadmap tracking and job notes. Readonly exclusion takes precedence in either decorator order; existing pre-call notifications and ordinary exception journaling remain unchanged. No unresolved specification ambiguity.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Successful non-readonly abort-decorated calls now publish normally; failed decorated calls stay out of the journal and propagate their exception, including false-valued exceptions. Ordinary failure journaling, pre-call notifications, and readonly exclusion in both decorator orders are preserved. Updated decorator and replication documentation. |
  | Commit | `fd31b31041db89c1b9c851b666c0be1e87ec5bb7` — implements F8 dispatch, regression tests, and documentation.; `358e93b93acb16349ef04a604361f9343d682d43` |
  | Validation | 106 tests passed on Python 3.12.2/macOS with DeprecationWarning as error; full suite used local socket access. Added 17 cases covering subscriber outcomes, exception identity, readonly orders, journal records, clock replay in a fresh process, and snapshot capture after failure. Final explicit outcome-table refinement: 15 unit cases passed. AIFlow roadmap check and git diff --check passed. |
  | Limitation | The decorator does not roll back in-memory mutations or external effects; later snapshots can retain failed-call mutations, and live replicas can differ after such failures. |
  | Limitation | Successful calls omitted by older code cannot be reconstructed from missing journal entries. |
  | Limitation | Other supported Python/OS combinations were not run locally. |
  | Next step | Run the supported Python and operating-system CI matrix. |

- [x] **F9 — Keep the previous checkpoint usable when snapshot creation fails.** `SnapshotManager.take_snapshot` opens the final numbered file before serialization succeeds; recovery then selects that incomplete file. Publish a snapshot only after a complete successful write, keeping incomplete work out of snapshot discovery. Accept with injected serialization/write failures and interruption before publication: the previous checkpoint remains loadable, necessary journals remain available, and successful checkpoint publication still passes F7's restart cases. Depends on F7 for coordinated journal boundaries.
  Complexity assessment before implementation: M; clear requirements across four implementation/tracking files in snapshot error handling, recovery fault injection, documentation, and roadmap tracking, plus job notes. F3 already supplies atomic publication and F7 supplies coordinated journal boundaries; preserve both and strengthen actual file-I/O and interruption coverage. No unresolved specification ambiguity; power-loss durability remains outside scope.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Preserved F3 atomic temporary-file publication and F7 journal coordination. Cleanup failures now log without hiding the snapshot error. Added actual file-write, flush, close, cleanup, and process-interruption regression coverage; previous checkpoint bytes and journals survive, and retry/restart restores writes exactly once. |
  | Commit | `06b59d477898274c7472258408b0b13af871c12c` — implements F9 cleanup hardening, failure coverage, and documentation; `72ed79bba8621ed6a367b73b3b38c9d06f3831c2` — prior F3 atomic publication and journal coordination.; `0a9809a34687ac999c9d5f7d9521b1a62f33be94` |
  | Validation | All 114 tests passed on Python 3.12.2/macOS with DeprecationWarning as error and local socket access, including F7 restart cases and 24 checkpoint tests. Faults cover serialization, partial write, flush, close, fsync, rotation, publication, cleanup, and process exit during write or before rotation/publication. AIFlow roadmap check and git diff --check passed. |
  | Limitation | Interrupted snapshots or failed cleanup can leave ignored temporary files; remove them only while the system is stopped. |
  | Limitation | Power-loss durability, pre-existing corrupted checkpoints, and mutations bypassing the proxy lock are outside this guarantee. Other supported Python/OS combinations were not run locally. |
  | Next step | Run the supported Python and operating-system CI matrix. |

- [x] **F10 — Provide a working persistence and recovery guide.** `docs/usage.rst` and `docs/tutorial.rst` use obsolete init_system signatures/imports; clock and replication examples also disagree with code. Replace them with current `coopy.base.init_persistent_system` examples covering close/reopen, `_clock`, readonly methods, snapshots, and decorator semantics. Accept when maintained examples execute in temporary directories, the Sphinx documentation builds, and replication is explicitly marked incomplete until F13. Explain mutable-object escape paths, trusted pickle storage, replay side effects, and the current durability contract without changing README.md.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Replaced obsolete guides with tested current APIs for close/reopen, clocks, readonly copies, checkpoints, and decorator outcomes. Documented trusted pickle storage, mutable escapes, replay effects, and durability limits; marked replication incomplete until F13. Added Sphinx CI and repaired the legacy theme. Estimated 15–18 files across docs/examples/checks; final scope was 20 implementation files, with no runtime or README changes. |
  | Commit | `9818b8fdb2ff9556fdf7583f512c7b3d0f844b57` — implements F10.; `9e4aa13d2e5c3d2301d6e912a093365d422b02b3` |
  | Validation | 118 tests passed on Python 3.12.2/macOS with DeprecationWarning as error and local sockets; final documentation checks: 4 passed, including a fresh-process reopen. Sphinx 8.2.3 HTML build passed with warnings as errors; AIFlow and git diff checks passed; README unchanged. |
  | Limitation | Replication remains experimental pending F13; the runnable example validates bootstrap only, not production recovery or failover. |
  | Limitation | Current recovery may continue after errors (F11), and ordinary journal completion has no synchronous power-loss durability guarantee (F12). |
  | Limitation | Hosted CI, other supported Python/OS combinations, and Sphinx 7 were not run locally. |
  | Next step | Run the hosted documentation job and supported Python/OS test matrix. |

### Implemented: recovery guarantees and slave bootstrap (planned as v0.6.0)

Originally a provisional later plan. Goal: callers can distinguish complete recovery from partial state and use replication with a defined synchronization boundary. Exit criterion: the selected recovery/durability contracts are documented and fault-tested, and a slave joining a populated master reaches matching state through concurrent updates.

- [x] **F11 — Make incomplete recovery visible to callers.** `restore.py` logs several decoding/replay failures and continues, while EOFError is always treated as ordinary end-of-file. Provide an explicit strict recovery path that refuses to expose a usable proxy after detected corruption or divergence, plus an explicitly chosen salvage path reporting what was recovered and where it stopped. Accept fixtures for a truncated record, corrupt middle record, missing method, originally successful action now failing, and originally failing action now succeeding; preserve expected exceptions and identify legacy actions lacking outcome metadata. Depends on F7 and F9 so checkpoint defects do not masquerade as recovery policy.
  Complexity assessment before implementation: M; Clear acceptance fixtures; estimated five implementation files across recovery, initialization, tests, and documentation, plus tracking and job notes. API ambiguities resolved with strict recovery by default and explicit salvage returning inspection state and a report. Boolean outcome compatibility is retained and legacy records are identified.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Strict initialization raises RecoveryError before exposing a proxy on detected corruption or divergence. Explicit salvage returns inspection state and a report with checkpoint, replay/expected-failure counts, legacy positions, and the first stopping file, offset, record, and method; it creates no journal. Final implementation: four files. |
  | Commit | `a0fe35f377532a709c8f129a1c30c6a11a07ed3c` — implements F11.; `5616ba96d12143179b3a62077ec6c11fe8f7eabb` |
  | Validation | Full suite: 132 passed on Python 3.12.2/macOS with DeprecationWarning as error and local socket access. Fourteen new recovery cases cover truncated/corrupt records, missing methods, both outcome reversals, expected exceptions, legacy metadata, invalid checkpoints, and salvage storage preservation. Sphinx warnings-as-errors, AIFlow, and git diff checks passed. |
  | Limitation | Legacy outcomes are unverified; current boolean metadata cannot compare exception types/messages or return values. Unsigned pickle cannot detect all corruption or whole-record removal and still requires trusted storage. |
  | Limitation | Salvage state can include mutations from the divergent attempted action, explicitly flagged in the report; replay side effects cannot be rolled back. Historical checkpoint-selection constraints remain unchanged. |
  | Next step | Run the supported Python and operating-system CI matrix. |

- [x] **F12 — Offer an explicit synchronous durability contract.** `RotateFileWrapper.write` flushes user-space buffers, but normal action completion does not call fsync; its close method simply closes the file. Add an opt-in synchronous policy that acknowledges a journaled mutation only after the configured disk synchronization succeeds, retaining a documented buffered mode. Accept fault-injected write/flush/fsync failures with no false success, observable synchronization in synchronous mode, and restart checks across journal rotation. Clearly report that a persistence failure may leave memory changed; do not promise rollback. Depends on F7 and F9 for coherent checkpoint handling.
  Complexity assessment before implementation: M; Clear fault and restart criteria; estimated seven implementation files across journal/file I/O, proxy guards, checkpoints, tests, and documentation, plus tracking and job notes. Policy ambiguity resolved with buffered default and opt-in sync using os.fsync; failures report potentially changed memory without rollback.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Added durability="sync" with complete-record flush/fsync before acknowledgment, synchronous close, and directory synchronization for journal creation/rotation and checkpoint publication. Buffered mode remains default. PersistenceError reports potentially changed memory and prevents further proxy mutations/checkpoints after journal failure. Final implementation: nine files. |
  | Commit | `e838fc7a1f19f2b380d445b9a4fe010746a4e8d3` — implements F12.; `5616ba96d12143179b3a62077ec6c11fe8f7eabb` |
  | Validation | Full suite: 152 passed on Python 3.12.2/macOS with DeprecationWarning as error and local socket access; final focused durability suite: 21 passed after adding checkpoint directory-sync failure coverage. Includes write/short-write/flush/fsync faults, close/setup/rotation failures, whole-record sync observation, and separate-process restart after os._exit across rotation/checkpoint. Sphinx warnings-as-errors, AIFlow, and git diff checks passed. |
  | Limitation | The contract is successful os.fsync, subject to POSIX filesystem/device guarantees; actual power loss and other Python/OS combinations were not tested. Unsupported directory sync fails instead of downgrading. |
  | Limitation | A persistence exception can leave memory changed and a record absent, partial, or fully persisted; it does not imply rollback or make blind retry safe. Snapshot directory sync can fail after the complete checkpoint becomes visible; prior files remain available. |
  | Next step | Run the supported Python/OS CI matrix and validate power-loss behavior on the intended deployment filesystem. |

- [x] **F13 — Bootstrap slaves from a consistent state and ordered updates.** Wire snapshot transfer and catch-up into the master/slave lifecycle so a late joiner receives existing state before subsequent actions and is not exposed as synchronized early. Accept an integration test with a populated master, a new slave, concurrent writes during transfer, and recorded clock values: after catch-up, state matches with no missing or duplicate actions. Authentication rejection, fragmented packets, and interrupted bootstrap must leave the slave explicitly unsynchronized. This remains trusted-peer replication; automatic failover and durable slave restart are outside this item's scope.
  Complexity assessment before implementation: M; clear acceptance criteria, with F5 already supplying snapshot capture and ordered catch-up. Estimated five core implementation/tracking files across lifecycle guards, transport, tests, and documentation, plus related guide corrections and job notes. Synchronization means all actions before the catch-up marker are applied; later updates remain asynchronous. Fragmented delivery must stay unsynchronized until the complete marker arrives.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | M |
  | Details | Accepted F5 snapshot/catch-up with a persistent populated master. Connection failure, shutdown, and cancellation retain unsynchronized guards; overlapping receivers and slave promotion are rejected. Explicit reconnect requires fresh bootstrap. Nine implementation files across runtime, tests, and documentation. |
  | Commit | `a25dfb129f8f97e0e8e600780c8438290769eae5` — implements F13 lifecycle hardening and acceptance coverage.; `15c7b551667698850b53fdb7deff829147f98629` |
  | Validation | 162 tests passed on Python 3.12.2/macOS with DeprecationWarning as error, including concurrent transfer writes, exact event/clock equality, fragmented authentication/snapshot delivery, interrupted action/ready packets, rejection, shutdown races, and reconnect. Sphinx warnings-as-errors, AIFlow, and git diff checks passed. |
  | Limitation | Trusted-peer compressed pickle protocol; upgrade master and slaves together. Live updates remain asynchronous; automatic reconnect/failover and durable slave restart are outside scope. |
  | Limitation | Pending queues are unbounded in memory and snapshot serialization pauses mutations. Direct object access and unlocked methods bypass proxy protection. Other supported Python/OS combinations were not run locally. |
  | Next step | Add a configurable pending-byte limit and disconnect slow slaves that exceed it. |
  | Next step | Run the supported Python and operating-system CI matrix. |

- [x] **F14 — Reject tampered journals and snapshots before unpickling.** Restore unpickles every journal record and snapshot without checking where it came from, so anyone who can write the data directory can run arbitrary code at the next restart. Add opt-in integrity protection, for example `init_persistent_system(obj, secret=...)`: each journal record and snapshot is written with an HMAC-SHA256 tag from the standard library, and restore verifies the tag before unpickling and stops with a clear error on any mismatch, missing tag or truncated tagged record. Without a secret, current files and behavior stay unchanged. Accept when a signed system restores normally across snapshots and journal rotation; flipping one byte in a journal record, swapping in a snapshot from another system or deleting a tag fails restore before any unpickling happens; using the wrong secret fails; and existing unsigned data directories still load when no secret is given. Document that the secret must be kept outside the data directory and that this detects tampering but does not encrypt data. Coordinates with F11, whose strict recovery path should report verification failures. Do not merge the 2014 `feature/secure_restore` draft (`5b2e614b72f284209697b58d708605cfeb4e3154`). It signs journal records with RSA through the unmaintained pycrypto, but never verifies them during restore, writes base64 bytes that the current restore cannot replay, and leaves snapshots unsigned.
  Complexity assessment before implementation: M; clear acceptance criteria; estimated eight files across initialization, integrity framing, journals, snapshots, recovery, tests, and docs. Ambiguities resolved by detecting same-secret cross-system snapshot swaps with a random identity and verifying all required data before any unpickling.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | M |
  | Details | Added opt-in secret bytes and standard-library HMAC-SHA256 envelopes bound to system identity, file name, and record offset. All selected restore bytes are verified and retained before any unpickling. Strict and salvage report verification failures; unsigned behavior is unchanged. Seven implementation files; no historical draft merged. |
  | Commit | `150b46ad6311e6c0460b71584bf097607016a8d1` — implements F14.; `67fa8422495d32e9db71200ee1f3e5b66346467a` |
  | Validation | 197 tests passed on Python 3.12.2/macOS with DeprecationWarning as error and local socket access, including 35 integrity cases. Covers tampering, tag removal/truncation, same-secret snapshot swaps, wrong secrets, unsigned compatibility, rotation/checkpoints, fresh-process restore, sync/faults, and verified-byte reuse. Sphinx warnings-as-errors, AIFlow, and git diff checks passed. |
  | Limitation | Integrity does not encrypt data or detect all valid rollback, whole-file deletion, or removal of complete trailing records; freshness requires trusted external state. Keep the secret outside storage and retain the identity in backups. |
  | Limitation | Signed recovery buffers selected storage in memory, and each signed action has an independent pickle memo. No automatic unsigned migration or key rotation; replication authentication is unchanged. |
  | Limitation | Other supported Python/OS combinations and actual power loss were not tested locally. |
  | Next step | Run the supported Python and operating-system CI matrix. |

### Implemented: modern Python (planned as v0.7.0)

Accepted roadmap scope from [FUTURE.md, Part 1](FUTURE.md#part-1--modern-python), covering all items 1.1–1.7. These entries are planned work, not implementation or release claims. Goal: improve typing, everyday API use, schema evolution, performance, concurrency, and contributor tooling while preserving plain domain objects and Python 3.10+ compatibility. Exit criterion: each item below meets its acceptance criteria, with compatibility and operational limits documented. Distribution and decentralization proposals in Parts 2 and 3 remain future work.

- [x] **F15 — Preserve domain types and separate persistence controls (1.1).** Type the class and instance forms of `init_persistent_system` so domain methods retain autocomplete and type checking. Add a separate `coopy.control(system)` persistence handle for operations such as `take_snapshot()`, `close()`, and replication controls; resolve collisions with domain methods named `close`, `shutdown`, or `take_snapshot`, while preserving the existing direct-control style for compatibility. Annotate the public API in `base.py`, `decorators.py`, `error.py`, and `integrity.py` first, then internals. Ship `py.typed`, preserve decorator signatures with `ParamSpec`, and use `TypeVar` syntax compatible with Python 3.10/3.11 rather than PEP 695 syntax. Introduce mypy or pyright in CI, tightening checks per module toward strict checking. Acceptance: installed-package typing examples retain domain signatures for both initialization forms and decorated methods; control-handle and name-collision tests pass, legacy controls remain usable, and the supported Python matrix imports the annotated package. Represent salvage results accurately in the overloads.
  Complexity assessment before implementation: L; clear requirements; estimated nine files across API typing, proxy dispatch, packaging, CI, and tests. Resolved control collisions by preferring domain methods; retained direct controls when no domain name collides.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | L |
  | Details | Added class/instance and strict/salvage overloads, ParamSpec decorators, py.typed, a typed control handle, domain-first control names, and staged mypy CI with installed-wheel examples. Fifteen implementation files. |
  | Commit | `aaff9ab1fa9ae725740499b770ca8521af9d6c4b` — implements F15.; `8b233e7305cd71f500611474666008a151162b47`; `72d5225974351e33ea417bac7ca3dd7f80505da9` |
  | Validation | 201 tests passed at the F15 commit; final suite 253 passed on Python 3.12.2/macOS. Six-module mypy and installed-wheel positive/negative signature checks passed, including dynamic recovery modes. Python 3.10.14 imports and persistence smoke passed. |
  | Limitation | Dynamic replay and networking internals are not yet strictly typed; proxy implementation attributes remain reserved. |
  | Limitation | The full Python 3.10–3.14 and Linux/macOS CI matrix was not run locally. |
  | Next step | Annotate remaining replay, journal, snapshot, and network internals and tighten mypy module checks. |
  | Next step | Run the hosted supported-Python and operating-system CI matrix. |

- [x] **F16 — Simplify the public API and resource lifecycle (1.2).** Add `coopy.open()` as the short entry point, retaining `init_persistent_system` as an alias. Support `with coopy.open(TodoList, "data/") as todo: ...`, closing journals and stopping the snapshot timer on normal and exceptional exit. Accept `str` and `os.PathLike` for `basedir` and use `pathlib.Path` internally. Introduce `start_primary`/`start_replica`, retaining `start_master`/`start_slave` as deprecated aliases for one or two releases with a documented removal schedule. Replace generic library failures with a precise `CoopyError` hierarchy. Leave logging configuration to applications and make the `coopy.log` file handler opt-in. Acceptance: lifecycle, path, exception, and alias tests pass; context-manager exceptions propagate after cleanup; default initialization creates no log file and explicit file logging still works. Document migration and compatibility behavior.
  Complexity assessment before implementation: L; clear requirements; estimated ten files across lifecycle, path handling, errors, replication aliases, tests, and documentation. Chose v0.9 for alias removal after v0.7/v0.8; typed context use goes through the control handle because Python has no arbitrary intersection type.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | L |
  | Details | Added coopy.open alias, direct and typed-control contexts, idempotent cleanup, timer/replication shutdown, native Path storage, nested directories, CoopyError subclasses, primary/replica names, and opt-in file logging. Seventeen implementation files. |
  | Commit | `23ba9eabb92b548a5c9e410f54aee87b36a4e1aa` — implements F16.; `8b233e7305cd71f500611474666008a151162b47` |
  | Validation | 212 tests passed at the F16 commit; final suite 253 passed. Normal/exceptional exits, cleanup failures, path variants, alias warnings, logging defaults/opt-in, typed contexts, and existing replication checks passed. Sphinx warnings-as-errors passed. |
  | Limitation | Direct with coopy.open works at runtime; use with coopy.control(coopy.open(...)) to retain domain typing in a context. |
  | Limitation | Deprecated master/slave methods remain available through v0.8; underlying OS errors and domain exceptions can still propagate in their original types. |
  | Next step | Remove start_master/start_slave aliases in v0.9 and update compatibility documentation. |

- [x] **F17 — Support serialization choices and schema evolution (1.3).** Introduce a pluggable serializer with pickle as the default and an opt-in safe format such as msgpack or JSON backed by a registry of allowed types. Store schema versions with journal actions and provide registered upcasters for changed method signatures, such as upgrading `add(text)` to `add(text, priority=0)`. Add class aliases for renamed or moved classes during unpickling. Acceptance: existing pickle storage remains readable; supported serializers round-trip snapshots and journals; renamed-class fixtures and old action schemas restore through registered migrations; unknown types, unsupported versions, and invalid upgrades fail explicitly through recovery policy. Document format selection, migration, and trust boundaries, including that F14 integrity protection does not make arbitrary pickle safe.
  Complexity assessment before implementation: XL; clear acceptance criteria with format/migration design choices; estimated ten files across every storage boundary. Chose explicit JSON registries, per-method consecutive action versions, caller-supplied pickle class aliases, and recovery-policy reporting; no automatic format guessing.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | XL |
  | Details | Added a typed serializer protocol, compatible pickle streams, registered JSON codecs, action schema metadata/upcasters, and pickle class aliases. Integrity preflight remains before decoding. Documented format selection, migrations, and trust boundaries. Twelve implementation files. |
  | Commit | `8741418ba1553b4b611fadf30eb9934e1f2101ee` — implements F17.; `8b233e7305cd71f500611474666008a151162b47` |
  | Validation | 41 serializer/migration tests and all 253 suite tests passed on Python 3.12.2/macOS. Covers signed/unsigned rotation and checkpoints, old schemas, moved classes in snapshots/arguments, invalid upgrades, custom codecs, and fresh-process JSON recovery. Mypy, installed-wheel typing, Sphinx, Python 3.10 smoke, diff checks, and AIFlow validation passed. |
  | Limitation | JSON supports trees and rejects cycles/shared container identities; named timezone identity is not retained and resource-exhaustion limits are not provided. |
  | Limitation | There is no automatic in-place format conversion or snapshot-state upcaster; explicit domain codecs and compatible pickle state restoration are required. |
  | Limitation | Replication still uses trusted-peer pickle and requires compatible domain/schema versions; disk upcasters do not migrate network traffic. HMAC does not make arbitrary pickle safe. |
  | Next step | Add explicit reference tags and validation before extending JSON to cyclic/shared object graphs. |
  | Next step | Add a separately tested export/import workflow for format and snapshot-state migrations. |

- [x] **F18 — Improve write throughput and snapshot performance (1.4).** Add group commit for `durability="sync"`, batching fsync for concurrent calls while acknowledging each mutation only after its batch is synchronized. Add POSIX fork-based snapshots using a copy-on-write view so the parent can continue serving writes; assess threaded-process and user-serialization safety, constrain child work to serialization and exit, and document supported configurations and fallback behavior. Offer snapshot compression through optional zstd/lz4 extras. Establish benchmarks for buffered/sync writes per second, restore time per million actions, and snapshot pause duration. Acceptance: publish reproducible before/after measurements, preserve checkpoint/replay ordering and synchronous acknowledgment guarantees under concurrent calls and injected failures, and round-trip compressed snapshots. Document fork restrictions and avoid performance promises unsupported by measurements.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | XL |
  | Details | Added opt-in sync group commit, parent-published POSIX copy-on-write snapshot jobs with guarded blocking fallback, zstd/lz4 extras, authenticated compression, and reproducible before/after benchmarks. Estimated 10–14 implementation files; delivered 14 plus four measurement artifacts. |
  | Commit | `1b2d9f06309c5e31d25b86139a0c59f1ec1f23e8` — implements F18.; `a26dd78c10536b16f2edc122e0362f3ce7681f6a` |
  | Validation | 294 tests passed; 30 native fork cases skipped on macOS. Separate controlled subprocess run: 40 passed, including all 30 fork cases with a test-only platform-guard bypass. Mypy, installed-wheel typing, Python 3.10 smoke, Sphinx, diff checks, and AIFlow validation passed. Actual million-action restores and write/pause samples published in docs/performance.rst and benchmarks/. |
  | Limitation | Native Linux execution and fork pause measurements were unavailable locally; controlled macOS mechanism tests do not certify Linux or production macOS safety. |
  | Limitation | Fork requires an explicitly audited single-threaded POSIX main process outside macOS; native threads, serializer callbacks, at-fork hooks, and external resources cannot be proven safe automatically. |
  | Limitation | A positive group-commit window adds isolated-call latency; measurements on this shared macOS host are noisy. Immediate per-call sync remains the default. |
  | Limitation | Signed/compressed snapshots buffer whole payloads in memory; there is no decompressed-size cap or measured compression speed/ratio. |
  | Next step | Run the Linux Python 3.10–3.14 CI matrix with both compression extras to verify the native fork path. |
  | Next step | Publish blocking-versus-fork pause and memory measurements on supported single-threaded Linux deployment hardware before claiming fork performance improvements. |

- [x] **F19 — Support asynchronous callers and free-threaded Python (1.5).** Add an asyncio facade such as `AsyncPersistent` that executes writes on one dedicated writer thread and exposes awaitable domain methods such as `await todo.add("milk")`, avoiding event-loop blocking on the proxy's `threading.RLock`. Add free-threaded Python 3.13t/3.14t CI coverage and document reader guarantees when the GIL no longer protects domain-object reads. Acceptance: asynchronous writes remain ordered and replay to the same state, event-loop responsiveness is tested during writes, shutdown and error propagation are defined, and free-threaded tests exercise concurrent readers and writers. Document the limits of direct object access and unlocked methods.
  Complexity assessment before implementation: L; clear acceptance criteria across an estimated 9–11 files in async dispatch/lifecycle, exports/typing, concurrency tests, CI, and docs. Unspecified cancellation, shutdown, and reader behavior were resolved as accepted work continuing, drain-and-join cleanup, and serialized queries.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | L |
  | Details | Added AsyncPersistent with one dedicated writer, ordered awaitable domain methods and queries, off-loop open/checkpoint/close, cancellation-safe accepted work, defined errors, and drain-and-join shutdown. Added GIL-disabled 3.13t/3.14t Linux/macOS CI and explicit reader/direct-access/unlocked guarantees. Ten implementation files. |
  | Commit | `091c7bac2acfebdc9ae4acb8cd34282719e8a2e2` — implements F19.; `55407ef5e8b8e44cab9622962224d0eb2f5520bd` |
  | Validation | Python 3.12.2/macOS: 308 passed, 31 skipped (30 native fork cases and one no-GIL assertion); includes 14 new async/concurrency cases. Seven-module mypy, installed-wheel typing, Python 3.10 async checkpoint/replay smoke, Sphinx warnings-as-errors, diff checks, and AIFlow validation passed. Full suite required local socket access. |
  | Limitation | Free-threaded interpreters were unavailable locally; the configured hosted jobs have not been executed here. Free-threaded CI omits optional compression extensions. |
  | Limitation | The queue is unbounded and has no forced shutdown timeout. Accepted writes continue after caller cancellation; applications must bound concurrency and await close before stopping the loop. |
  | Limitation | The facade belongs to one event loop, exposes synchronous public domain methods with dynamic typing, and offers blocking checkpoints only; timer and replication controls are not exposed. A positive group-commit delay adds latency without batching facade calls. |
  | Next step | Run the four hosted Python 3.13t/3.14t Linux/macOS jobs and verify the GIL-disabled assertions and concurrent reader/writer tests pass. |

- [x] **F20 — Strengthen development tooling and generated documentation (1.6).** Adopt ruff linting and formatting in CI and pre-commit. Add Hypothesis property-based tests generating sequences of method calls, snapshots, and restarts, asserting that restored state equals live state. Establish a measured coverage baseline and a CI gate that prevents regression. Configure Dependabot for GitHub Actions versions. Keep Sphinx and generate an API reference from the type hints. Acceptance: lint/format and property checks run in CI, coverage below the agreed baseline fails the gate, the Actions update configuration is valid, and the generated reference builds with warnings treated as errors.
  Complexity assessment before implementation: M; clear requirements across about ten tooling, test, and documentation files, plus mechanical formatting of roughly 59 Python files. Components: lint/pre-commit, CI/dependencies, persistence property tests, coverage policy, and Sphinx API generation. The unspecified coverage threshold uses the measured full-package baseline rounded down to 93%; no alternate target was supplied.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | M |
  | Details | Added pinned Ruff lint/import sorting/formatting and pre-commit hooks, CI quality/release gates, eight Hypothesis state-machine configurations, malformed-storage regression tests, a measured 93% package coverage floor, weekly Actions Dependabot updates, and Sphinx autosummary/autodoc from annotations and overloads. Applied the formatter across existing Python sources; 65 implementation files. |
  | Commit | `573682037d9405dbba6f18bd9373ff0fe55fc593` — implements F20.; `375097e3b4eefdc164e1a97d77e96a1975dd1617` |
  | Validation | Python 3.12.2/macOS: 329 passed, 31 skipped; coverage 93.27% (1,747/1,873 statements), with a verified failing under-coverage gate. Ruff and both pre-commit hooks passed. Mypy, installed-wheel typing, Python 3.10 syntax/recovery smoke, YAML schema validation, clean staged-source Sphinx warnings-as-errors, diff checks, and AIFlow validation passed. The property oracle rejected an injected lost journal tail. |
  | Limitation | Coverage is a fixed line-coverage floor, not an automatic ratchet or branch/subprocess coverage; network cleanup timing can slightly change results. |
  | Limitation | Generated properties cover sequential clean restarts, not power loss or concurrent schedules; existing fault/concurrency tests remain. Dynamic domain methods and unannotated internals cannot provide a complete typed API reference. |
  | Limitation | Hosted Linux/macOS Python 3.10–3.14 and free-threaded jobs were not run here; native fork and GIL-disabled assertions account for local skips. Dependabot pull-request creation requires the configuration on the default branch and was not observed locally. |
  | Next step | Run the hosted CI matrix to confirm coverage and stateful tests on every supported interpreter/platform, including native Linux fork and free-threaded jobs. |
  | Next step | Install the pre-commit hooks in contributor checkouts and review the first scheduled Dependabot Actions update after pushing to the default branch. |

- [x] **F21 — Harden password comparison and remove empty network backends (1.7).** Replace the replication password's ordinary inequality comparison with `hmac.compare_digest`. Document that the password is still transmitted in plain text and remains a stopgap pending the encrypted transport proposed in FUTURE.md §2.2. Delete the empty `coopy/network/linux_epoll.py` and `coopy/network/osx_kqueue.py` placeholders; use standard-library `selectors` or a future pyzmq transport if platform-specific polling is needed. Acceptance: valid and invalid password authentication tests pass with constant-time comparison, no imports depend on the deleted modules, and documentation does not imply transport encryption.
  Complexity assessment before implementation: S; clear requirements affecting five implementation files across authentication, tests, transport documentation, and two backend deletions, plus roadmap tracking. The polling wording is interpreted as future guidance; the existing select backend needs no rewrite.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | S |
  | Details | Authentication uses hmac.compare_digest; removed both empty platform backends. Replication documentation explicitly describes plaintext passwords and payloads, the stopgap handshake, and future selectors/pyzmq options. |
  | Commit | `a6e3ee195e06b534a598a5312637d23a0c159af6` — implements F21.; `abb219c2fe0f3582c7d8d9b49a12ccb407db5fd6`; `72d5225974351e33ea417bac7ca3dd7f80505da9` |
  | Validation | Python 3.12.2/macOS: 335 passed, 31 skipped; coverage 93.33% exceeds the 93% floor. Six new real-socket cases verify compare_digest delegation for valid, first/last-byte mismatch, empty, longer, and non-ASCII passwords. Existing bootstrap/rejection tests pass. Ruff lint/format, strict Sphinx build, deleted-backend import audit, diff checks, and AIFlow validation passed. Socket tests required execution outside the sandbox. |
  | Limitation | Passwords and replication payloads remain unencrypted; shared-password authentication is a stopgap, and pickle replication requires trusted peers on a trusted network. |
  | Limitation | Local validation covers Python 3.12/macOS; 30 native Linux fork cases and one free-threaded assertion were skipped. The hosted platform/interpreter matrix was not run here. |
  | Next step | Implement the encrypted transport proposed in FUTURE.md §2.2 as a separate feature. |


### Release blockers

These items change the on-disk format or protect data, so they must land before the first release creates data that later versions have to read.

- [x] **F22 — Enforce one writer per data directory.** The documentation says to use one process and one persistent proxy per data directory, but nothing enforces it: opening the same directory twice in one process returns two writable proxies, and both journal writes without error (reproduced 2026-10-10). Two processes would interleave journal records silently. Hold an exclusive lock for the lifetime of a writable system: a lock file in the data directory locked with `fcntl.flock` on POSIX and `msvcrt.locking` on Windows, released by `close()`, the context manager and process exit. A second open of the same directory, in the same or another process, raises a new `LockError` (subclass of `LifecycleError`) naming the directory and, where available, the holder's PID. Salvage recovery is read-only and must not take the lock. Acceptance: same-process and cross-process double opens fail; close, context-manager exit and a killed holder release the lock; salvage works while a writer holds the lock; `AsyncPersistent` and replicas follow the same rule. Document that network filesystems may not honor advisory locks.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | M |
  | Details | New `coopy/locking.py` `DirectoryLock` holds `coopy.lock` (PID inside) via `fcntl.flock`/`msvcrt.locking` plus an in-process registry keyed by resolved path; `init_persistent_system` takes it before any write and releases it on failed opens; `close()`/context exit release it; new `coopy.error.LockError(LifecycleError)` names the directory and holder PID. Salvage takes no lock. Docs (README, usage, index, modern-api, api, changelog) updated, including the network-filesystem caveat. Spec was clear; ~10 files. |
  | Commit | `b883c0d14cd7ba338c430dea681450ed7ba4db2f` — implements F22.; `1045234049c60bdde2644b3e1573de88dbe85001` |
  | Validation | New `tests/functional/test_locking.py` (10 tests: same/cross-process, equivalent paths, close, context exit, failed open, SIGKILLed holder, salvage, AsyncPersistent, replicas) passes; full suite 345 passed, 31 skipped; ruff check/format clean; Sphinx -W build clean; mypy shows no errors in changed files (pre-existing errors elsewhere). |
  | Limitation | The Windows `msvcrt.locking` path is untested: CI and local runs cover only macOS/Linux. |
  | Limitation | Advisory locks may not be honored on network filesystems (NFS, SMB); only documented, not detected. |
  | Limitation | A forked snapshot child inherits the lock descriptor, so a killed parent's lock is freed only once that child exits. |
  | Next step | Add a Windows CI job to exercise the `msvcrt.locking` path and holder-PID reporting. |

- [x] **F23 — Version the on-disk format.** Only HMAC-signed files carry a magic header (`COOPY-HMAC-1`); plain pickle and JSON journals and snapshots have no marker, so a future format change cannot be told apart from corruption. Write a small manifest (for example `coopy.json` with format version, serializer name, signing on/off and creating coopy version) when a data directory is created, and refuse to open a directory whose format version is newer than the running library with a clear error. Directories without a manifest are treated as legacy format 0 and remain readable; the manifest is written on the next writable open. Acceptance: new directories get a manifest; legacy 0.3/0.4/0.5 fixtures still restore; a future-version manifest fails before any decoding; switching serializer or signing against an existing manifest fails with a clear message instead of a decode error. Coordinates with F22 so the manifest is written under the lock.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | M |
  | Details | New `coopy/manifest.py` writes `coopy.json` (format_version 1, serializer, signed, coopy_version) atomically under the F22 lock: before the first checkpoint of a new directory, or after a clean restore of a legacy (format 0) one. `recover()` checks it before decoding, so strict, salvage and `restore()` raise new `coopy.error.FormatError` for newer/unreadable manifests and serializer or signing mismatches. Serializers name themselves via a `format_name` class attribute (`pickle`, `json`). Committed 0.3.1, 0.4b and 0.5.0 fixtures. Spec was clear; ~15 files. |
  | Commit | `06572eb4bdc46f6d5911a943c6456ce4188d1946` — implements F23.; `404d138f152e74b1b33e7da389b6dcc36bc0ef97` |
  | Validation | New `tests/functional/test_manifest.py` (manifest contents, legacy fixtures restore and upgrade, future version with Unpickler forbidden, corrupt manifest, serializer/signing switches, lock coverage) passes; full suite 366 passed, 31 skipped; ruff check/format clean; Sphinx -W build clean. Three existing tests now remove the manifest to keep covering legacy-directory behavior. |
  | Limitation | Custom serializers without a `format_name` are recorded as `custom:<class path>` and never compared, so switching to or from them is still caught only by decoding. |
  | Limitation | 0.3.1 and 0.4b fixtures were generated by those releases' sources under Python 3.9, not Python 2; they hold what those releases restore (their post-checkpoint write loss is preserved). |
  | Limitation | A crash between creating a new directory's manifest and its first checkpoint leaves a manifest-only directory, which reopens normally. |
  | Next step | Have F27's conversion command write the target manifest and F28's key rotation keep `signed` in sync. |

- [x] **F24 — Document migrating snapshot state.** F17 upgrades journal actions and maps renamed classes, but a snapshot taken before a domain class gained, renamed or restructured a field loads with the old shape. Until F26 adds first-class support, document the supported pattern: a class-level state version plus `__setstate__` that upgrades old dictionaries, with a worked example (adding a field with a default, renaming a field, splitting one field into two) and a test that restores a committed old-format snapshot fixture. Acceptance: the example runs in the documentation tests against a stored fixture, and the migration guide explains when to use action upcasters, class aliases or `__setstate__`.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-10 |
  | Complexity | M |
  | Details | New `docs/migrations.rst` guide (in the toctree, linked from modern-api) with a table for choosing action upcasters, class aliases or a versioned `__setstate__`. `docs/examples/address_book.py` evolves `Contact` through four state versions (add `email` default, rename `phone`→`telephone`, split `name`); `state_migration.py` restores the committed `docs/examples/fixtures/address_book_v1` snapshot plus a v1 journal call (with an `add` upcaster), snapshots and reopens. `scripts/make_state_migration_fixture.py` regenerates the fixture. Spec was clear; "migration guide" had no existing page, so one was added. ~10 files. |
  | Commit | `413a34fa9b4f83716b942e9824d1c54d25d210a8` — implements F24. |
  | Validation | test_documentation.py runs the example against the stored fixture, guards the fixture's v1 shape, and checks the rewritten snapshot carries state_version 4 and newer versions are rejected (7 passed). Full suite 354 passed, 46 skipped (fork, free-threaded, missing zstd/lz4 extras); ruff check/format clean; Sphinx -W build clean. Strict/salvage handling of a failing `__setstate__` checked manually. |
  | Limitation | The state version is a user convention (`STATE_VERSION` key in pickled state); coopy neither records nor validates it, and JSON storage needs the same logic in registered decoders. |
  | Limitation | The fixture was generated by the current coopy (manifest format 1) from a v1 domain module, not by an older coopy release. |
  | Next step | Implement F26 registered state upgraders and keep this `__setstate__` example passing under them. |

- [ ] **F25 — Prepare and publish 0.6.0.** Set `__version__ = "0.6.0"` and the Sphinx `version`; fold the changelog's 0.5.0 and Unreleased sections into a dated 0.6.0 entry with an "Upgrading" section listing breaking changes (strict recovery by default, the new replication handshake, the `start_master`/`start_slave` deprecations and their v0.9 removal). Verify the PyPI trusted publisher for `felipecruz/coopy`, workflow `ci.yml`, environment `pypi`. Rebase and merge or close the open Dependabot pull requests. Remove stale references to deleted `.aiflow` notes. Acceptance: hosted CI is green on the release commit, `v0.6.0` publishes, a fresh `pip install coopy==0.6.0` imports and completes a persistence round trip, and the README badges resolve.

## v0.7.0 — Migrations and operations

Planned. Goal: users can evolve their data, manage disk usage and inspect storage without writing custom scripts. Exit criterion: each item meets its acceptance checks with documentation and tests against stored fixtures from 0.6.0.

- [ ] **F26 — Migrate snapshot state with registered upgraders.** Record a domain state version in each snapshot (from a class attribute such as `__coopy_version__`) and let applications register upgraders, mirroring F17's `ActionSchemas`: `StateSchemas().register(TodoList, from_version=1, upgrade=fn)`. Recovery applies upgraders in order before replay; unknown or missing versions fail through the recovery policy. Acceptance: 0.6.0 snapshot fixtures upgrade across several versions; strict mode fails on a missing upgrader and salvage reports it; F24's `__setstate__` pattern keeps working.

- [ ] **F27 — Convert a data directory between formats.** The modern API guide states that changing formats "requires an explicit export/import to a new directory; no conversion command is provided". Add `coopy.convert(src, dst, *, serializer=..., secret=..., new_secret=...)` that recovers `src` strictly, writes a fresh checkpoint to an empty `dst` with the target serializer and signing, and never modifies `src`. Acceptance: pickle→JSON, JSON→pickle, unsigned→signed and signed→unsigned round trips restore identical state; non-empty destinations and failed recovery leave nothing behind.

- [ ] **F28 — Rotate integrity secrets.** F14 has no key rotation: changing the secret makes existing signed storage unreadable. Support reading with a list of accepted secrets while writing with the newest, and provide an explicit re-sign path (through F27) after which old secrets can be retired. Acceptance: a directory signed with key A opens with `[B, A]`, new records are signed with B, re-signing removes the dependence on A, and wrong or retired keys still fail before decoding.

- [ ] **F29 — Prune old snapshots and journals.** Every snapshot and journal is kept forever, so disk use only grows. Add `coopy.control(system).prune(keep=N)` (and an optional `keep_for=timedelta`) that deletes checkpoints older than the newest N together with journals no longer needed to replay from the oldest kept checkpoint. Never delete the files needed to recover the current state; take the F22 lock. Acceptance: recovery after pruning matches live state; pruning during concurrent writes and snapshot publication is safe; signed directories stay verifiable.

- [ ] **F30 — Add a command-line tool.** Inspecting or maintaining a directory currently requires Python code. Add `python -m coopy` with `inspect DIR` (files, checkpoint, action counts, format manifest), `verify DIR` (strict recovery without writing; non-zero exit on failure), `log DIR` (list journaled actions with method names, arguments summary and recorded times), `snapshot DIR CLASS`, `prune DIR --keep N` and `convert SRC DST`. Commands that load data must state that they unpickle trusted data and require the domain module on `PYTHONPATH`. Acceptance: each command is tested against fixtures, honors F22 locking, and exits non-zero on errors.

- [ ] **F31 — Restore to a point in time.** The journal already holds everything needed to rebuild past states. Add read-only recovery up to a bound: `coopy.open(..., recovery="salvage", until=ActionRef | datetime)` or a dedicated `coopy.replay(..., until=...)`, using recorded clock values for time bounds. Acceptance: state at action N or time T matches a live capture taken at that point; bounds before the oldest kept checkpoint fail clearly; nothing is written.

- [ ] **F32 — Optionally snapshot on close.** `close()` never takes a snapshot, so every restart replays the whole journal since the last checkpoint. Add `close(snapshot=True)` and a matching context-manager option, keeping the current default. Acceptance: with the option, the next open replays no actions; snapshot failures during close are reported and leave the previous checkpoint usable.

## v0.8.0 — Transactions

Planned. Goal: domain methods that fail can leave state unchanged instead of partially mutated. Exit criterion: the chosen design is documented with its cost, and the opt-in mechanism passes fault tests.

- [ ] **F33 — Roll back in-memory changes when a call fails.** `@abort_exception` keeps a failing call out of the journal but leaves its in-memory mutations in place, and synchronous-durability persistence failures can likewise leave memory changed. Evaluate copy-on-write or snapshot-and-restore rollback, choose an opt-in mechanism (for example `@transactional` or a per-system policy), and document its memory and latency cost. Acceptance: a failing transactional call leaves state equal to the state before the call, live and after restart; non-transactional behavior is unchanged; nested calls and replicas are defined.

## Validation record

Checks ran against a temporary copy of current source/tests using the existing repository virtual environment, without installs, services, or network calls. The README and starter hashes were recorded; the target was reread immediately before replacement. `make test` was not invoked because it first runs a destructive clean target. Its pytest step was adapted to exclude socket activity and repository cache writes:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/felipecruz/Projects/coopy/.venv/bin/python -m pytest --verbose -W error::DeprecationWarning -p no:cacheprovider --ignore=tests/unit/test_network_select.py -k 'not start_master and not master_accepts_writes and not start_slave'
```

Result: **52 passed, 3 deselected**, with the nine socket tests in the ignored module not collected. This is a focused run, not the full CI matrix or a coverage measurement; the old coverage table in `docs/tests.rst` was not treated as current evidence.

Additional temporary Python probes invoked the real library: creating `before`, taking a snapshot, then creating `after` restored only `before`; a successful abort-decorated counter increment restored 0 instead of 1; serializing an object whose `__reduce__` raises left a newer snapshot that made recovery raise EOFError. A `tomllib` metadata check in the temporary source copy confirmed the declared README path does not exist in that checkout; the later untracked replacement was not part of the check. These failures establish F7–F9 and F6; no fixes were made. Build/install checks remain unverified because the existing environment lacks setuptools, build, and twine; no dependencies were installed. Replication, crash/power-loss behavior, historical pickle compatibility, and published artifacts were not validated.

AIFlow validation used `'/Users/felipecruz/Projects/aiflow/build/AIflow.app/Contents/MacOS/MarkdownPreview' --check '/Users/felipecruz/Projects/coopy/ROADMAP.md'`: **0 errors, 2 warnings**. Both warnings recommend marking partial items with implementation commits Done. F3 and F5 deliberately retain Partial status and their provenance because the corresponding recovery/synchronization outcomes are incomplete; marking them Done would contradict the evidence.

Open decisions at the time of this audit (since resolved by F11, F12 and F17): choose whether strict recovery becomes the default or stays opt-in, define how synchronous durability interacts with existing buffered behavior, and decide which historical pickle formats merit explicit migration support before making compatibility promises.

## Implementation validation — 2026-10-09

Job BE4A3268-73C5-40D5-ABB5-4B0F5AAB00A8 implemented the selected F3 and F5 items in separate commits, with complexity assessed as L for each before implementation. Their tables above supersede the earlier audit's recovery and bootstrap findings. Unselected items and their version placement remain unchanged; F7/F9/F13 supplied acceptance criteria for this job, rather than separate implementation selections.

The final full-suite command was `.venv/bin/python -m pytest -q -W error::DeprecationWarning`: **83 passed** on local Python 3.12.2. Socket checks ran with local network permissions after the sandbox rejected binding; both TCP and Unix-socket integration checks passed. The suite includes a real subprocess exit before checkpoint publication. It does not verify power-loss behavior or the multi-platform CI matrix. `git diff --check` passed, and the AIFlow MarkdownPreview roadmap check reported **OK, with no errors or warnings** before the tracking commit.

Upgrade/readiness instructions and remaining operational caveats are recorded in `docs/snapshots.rst` and `docs/replication.rst`. The job's AIFlow notes file was removed from the repository on 2026-10-10. No implementation blockers remain; limitations and follow-up actions are listed separately in the selected items' tables.
