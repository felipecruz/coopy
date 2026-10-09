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

- [x] **F3 — Recover reliably across manual and timed snapshots.** Post-snapshot writes survive restart, and failed snapshots retain the previous usable checkpoint, covering the recovery scenarios specified in F7 and F9.
  Complexity assessment before implementation: L; clear requirements across roughly seven code/test files in snapshot publication, journal rotation, and recovery. Historical broken checkpoint boundaries cannot be inferred safely; retain existing file interpretation and test legacy streams.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | L |
  | Details | Atomic temporary-file publication advances journals under the domain lock before exposing a checkpoint. Reopening creates a fresh journal; rotation occurs between complete records. Timer failures are logged and retried. |
  | Commit | `72ed79bba8621ed6a367b73b3b38c9d06f3831c2` — implements F3 recovery; prior snapshot groundwork: `b14bd7d83b9a5913079f4b29c61d9e98b02c167d`, `76279581872c5d3d768355e2f2126d09b8020730`. |
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
  | Commit | `194b6b4b8366c5be40abf01e2d8f7873ddfc749a` — implements F5 bootstrap and catch-up; prior transport groundwork: `d9921b3a6e8e3bd1bd677097a44430d77bdd469d`, `76279581872c5d3d768355e2f2126d09b8020730`. |
  | Validation | Full suite: 83 passed on Python 3.12 with DeprecationWarning as error, including populated-master concurrent catch-up, live replay, recorded clocks, readonly guards, fragmented authentication/packets, rejection, interrupted bootstrap, replay divergence, and TCP/Unix shutdown. |
  | Limitation | Length-prefixed authentication and the ready marker require upgrading master and slaves together; old peers are incompatible. |
  | Limitation | Slow-slave queues are unbounded in memory; snapshot serialization still pauses master mutations. |
  | Limitation | Trusted-peer replication only; durable slave restart, automatic reconnect/failover, and synchronous acknowledgments are outside scope. Successful abort-decorated calls remain unpublished pending F8. |
  | Next step | Bound pending replication bytes per slave and disconnect clients exceeding the configured limit. |
  | Next step | Run the supported Python and operating-system CI matrix; this job validated local Python 3.12 only. |

## v0.5.1 — Make installation and local recovery dependable

Planned corrective version, not a release claim. Goal: users can install the package and retain successful local changes through snapshots and clean restarts. Exit criterion: F6–F10 acceptance checks pass, with regression coverage for the three reproduced persistence failures and accurate executable documentation.

- [x] **F6 — Build distributions with the actual README.** At the original audit, `pyproject.toml` pointed to `README.markdown`, absent from HEAD after its rename to `README.md`. An untracked replacement appeared during that audit; preserve and reconcile that work when fixing metadata, while preserving `README.md` content. Accept when sdist and wheel build, `twine check --strict` passes, both include the expected project description, and installation from the built artifacts can import coopy and complete a temporary-directory persistence round trip.
  Complexity assessment before implementation: M; clear acceptance criteria across two implementation/tracking files, plus job notes; distribution validation and existing CI integration are the affected components. This job strengthens the installed-artifact round trip to restore in a fresh Python process. The stale metadata and replacement README were already reconciled in `986fecea236ea415207c1eddc0b9b1218f6f97b4`; preserve the current README verbatim and validate that result. No unresolved specification ambiguity.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Preserved the reconciled README.md and correct metadata path. Existing CI validates both artifact descriptions and installs each into a fresh environment; the round trip now writes a checkpoint and later journal entry, closes, exits, and restores both in a separate isolated Python process. |
  | Commit | `e6b0beb5afb3af651682e64b80f0d3b1ccc44204` — implements F6 process-restart validation; `ed54c62fae85316b848df09f871ee6e46635979a` — prior artifact validation and CI; `986fecea236ea415207c1eddc0b9b1218f6f97b4` — prior README reconciliation and metadata fix; `b4ac94cd052223008bdfa803e7d3b07841598087` — prior tracking only. |
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
  | Commit | `f9e3375dba4251d30ec4fe1063a99df6be4de0c8` — implements F7 regression coverage and boundary documentation; `72ed79bba8621ed6a367b73b3b38c9d06f3831c2` — prior F3 runtime checkpoint fix and recovery tests. |
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
  | Commit | `fd31b31041db89c1b9c851b666c0be1e87ec5bb7` — implements F8 dispatch, regression tests, and documentation. |
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
  | Commit | `06b59d477898274c7472258408b0b13af871c12c` — implements F9 cleanup hardening, failure coverage, and documentation; `72ed79bba8621ed6a367b73b3b38c9d06f3831c2` — prior F3 atomic publication and journal coordination. |
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
  | Commit | `9818b8fdb2ff9556fdf7583f512c7b3d0f844b57` — implements F10. |
  | Validation | 118 tests passed on Python 3.12.2/macOS with DeprecationWarning as error and local sockets; final documentation checks: 4 passed, including a fresh-process reopen. Sphinx 8.2.3 HTML build passed with warnings as errors; AIFlow and git diff checks passed; README unchanged. |
  | Limitation | Replication remains experimental pending F13; the runnable example validates bootstrap only, not production recovery or failover. |
  | Limitation | Current recovery may continue after errors (F11), and ordinary journal completion has no synchronous power-loss durability guarantee (F12). |
  | Limitation | Hosted CI, other supported Python/OS combinations, and Sphinx 7 were not run locally. |
  | Next step | Run the hosted documentation job and supported Python/OS test matrix. |

## v0.6.0 — Expose recovery guarantees and complete slave bootstrap

Provisional later plan, not a scheduled release. Goal: callers can distinguish complete recovery from partial state and use replication with a defined synchronization boundary. Exit criterion: the selected recovery/durability contracts are documented and fault-tested, and a slave joining a populated master reaches matching state through concurrent updates.

- [x] **F11 — Make incomplete recovery visible to callers.** `restore.py` logs several decoding/replay failures and continues, while EOFError is always treated as ordinary end-of-file. Provide an explicit strict recovery path that refuses to expose a usable proxy after detected corruption or divergence, plus an explicitly chosen salvage path reporting what was recovered and where it stopped. Accept fixtures for a truncated record, corrupt middle record, missing method, originally successful action now failing, and originally failing action now succeeding; preserve expected exceptions and identify legacy actions lacking outcome metadata. Depends on F7 and F9 so checkpoint defects do not masquerade as recovery policy.
  Complexity assessment before implementation: M; Clear acceptance fixtures; estimated five implementation files across recovery, initialization, tests, and documentation, plus tracking and job notes. API ambiguities resolved with strict recovery by default and explicit salvage returning inspection state and a report. Boolean outcome compatibility is retained and legacy records are identified.

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | 2026-10-09 |
  | Complexity | M |
  | Details | Strict initialization raises RecoveryError before exposing a proxy on detected corruption or divergence. Explicit salvage returns inspection state and a report with checkpoint, replay/expected-failure counts, legacy positions, and the first stopping file, offset, record, and method; it creates no journal. Final implementation: four files. |
  | Commit | `a0fe35f377532a709c8f129a1c30c6a11a07ed3c` — implements F11. |
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
  | Commit | `e838fc7a1f19f2b380d445b9a4fe010746a4e8d3` — implements F12. |
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
  | Commit | `a25dfb129f8f97e0e8e600780c8438290769eae5` — implements F13 lifecycle hardening and acceptance coverage. |
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
  | Commit | `150b46ad6311e6c0460b71584bf097607016a8d1` — implements F14. |
  | Validation | 197 tests passed on Python 3.12.2/macOS with DeprecationWarning as error and local socket access, including 35 integrity cases. Covers tampering, tag removal/truncation, same-secret snapshot swaps, wrong secrets, unsigned compatibility, rotation/checkpoints, fresh-process restore, sync/faults, and verified-byte reuse. Sphinx warnings-as-errors, AIFlow, and git diff checks passed. |
  | Limitation | Integrity does not encrypt data or detect all valid rollback, whole-file deletion, or removal of complete trailing records; freshness requires trusted external state. Keep the secret outside storage and retain the identity in backups. |
  | Limitation | Signed recovery buffers selected storage in memory, and each signed action has an independent pickle memo. No automatic unsigned migration or key rotation; replication authentication is unchanged. |
  | Limitation | Other supported Python/OS combinations and actual power loss were not tested locally. |
  | Next step | Run the supported Python and operating-system CI matrix. |

## Validation record

Checks ran against a temporary copy of current source/tests using the existing repository virtual environment, without installs, services, or network calls. The README and starter hashes were recorded; the target was reread immediately before replacement. `make test` was not invoked because it first runs a destructive clean target. Its pytest step was adapted to exclude socket activity and repository cache writes:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/felipecruz/Projects/coopy/.venv/bin/python -m pytest --verbose -W error::DeprecationWarning -p no:cacheprovider --ignore=tests/unit/test_network_select.py -k 'not start_master and not master_accepts_writes and not start_slave'
```

Result: **52 passed, 3 deselected**, with the nine socket tests in the ignored module not collected. This is a focused run, not the full CI matrix or a coverage measurement; the old coverage table in `docs/tests.rst` was not treated as current evidence.

Additional temporary Python probes invoked the real library: creating `before`, taking a snapshot, then creating `after` restored only `before`; a successful abort-decorated counter increment restored 0 instead of 1; serializing an object whose `__reduce__` raises left a newer snapshot that made recovery raise EOFError. A `tomllib` metadata check in the temporary source copy confirmed the declared README path does not exist in that checkout; the later untracked replacement was not part of the check. These failures establish F7–F9 and F6; no fixes were made. Build/install checks remain unverified because the existing environment lacks setuptools, build, and twine; no dependencies were installed. Replication, crash/power-loss behavior, historical pickle compatibility, and published artifacts were not validated.

AIFlow validation used `'/Users/felipecruz/Projects/aiflow/build/AIflow.app/Contents/MacOS/MarkdownPreview' --check '/Users/felipecruz/Projects/coopy/ROADMAP.md'`: **0 errors, 2 warnings**. Both warnings recommend marking partial items with implementation commits Done. F3 and F5 deliberately retain Partial status and their provenance because the corresponding recovery/synchronization outcomes are incomplete; marking them Done would contradict the evidence.

Open decisions for v0.6.0: choose whether strict recovery becomes the default or stays opt-in, define how synchronous durability interacts with existing buffered behavior, and decide which historical pickle formats merit explicit migration support before making compatibility promises.

## Implementation validation — 2026-10-09

Job BE4A3268-73C5-40D5-ABB5-4B0F5AAB00A8 implemented the selected F3 and F5 items in separate commits, with complexity assessed as L for each before implementation. Their tables above supersede the earlier audit's recovery and bootstrap findings. Unselected items and their version placement remain unchanged; F7/F9/F13 supplied acceptance criteria for this job, rather than separate implementation selections.

The final full-suite command was `.venv/bin/python -m pytest -q -W error::DeprecationWarning`: **83 passed** on local Python 3.12.2. Socket checks ran with local network permissions after the sandbox rejected binding; both TCP and Unix-socket integration checks passed. The suite includes a real subprocess exit before checkpoint publication. It does not verify power-loss behavior or the multi-platform CI matrix. `git diff --check` passed, and the AIFlow MarkdownPreview roadmap check reported **OK, with no errors or warnings** before the tracking commit.

Upgrade/readiness instructions and remaining operational caveats are recorded in `.aiflow/notes/NOTES_BE4A3268-73C5-40D5-ABB5-4B0F5AAB00A8.MD`, `docs/snapshots.rst`, and `docs/replication.rst`. No implementation blockers remain; limitations and follow-up actions are listed separately in the selected items' tables.
