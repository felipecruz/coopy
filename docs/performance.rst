Persistence performance measurements
====================================

F18 adds group commit, optional snapshot compression, and an opt-in POSIX fork
path. These are workload-dependent options, not a throughput or pause guarantee.
See :doc:`usage` for acknowledgment semantics and :doc:`snapshots` for fork safety.

Reproduce
---------

Run ``scripts/benchmark_persistence.py`` from the repository root. It imports
coopy from ``PYTHONPATH`` so the same harness can measure an older checkout.
For the baseline used here::

    mkdir -p /tmp/coopy-f18-baseline
    git archive 8b233e7305cd71f500611474666008a151162b47 | tar -x -C /tmp/coopy-f18-baseline
    TZ=UTC PYTHONPATH=/tmp/coopy-f18-baseline .venv/bin/python scripts/benchmark_persistence.py
    TZ=UTC PYTHONPATH=. .venv/bin/python scripts/benchmark_persistence.py --group-commit-delay 0.001

Run commands sequentially on the same machine/filesystem with other workloads
idle. Repeat on deployment hardware. Pass ``--directory /path/on/test/device``
to select a filesystem; otherwise storage uses the system temporary directory.
Repeat both commands with ``--workers 1 --writes 1000 --actions 10000`` for the
single-caller latency trade-off. Install the package/test environment as usual;
the benchmark itself uses only the standard library. The after revision is the
F18 implementation commit explicitly recorded in ``ROADMAP.md``.

The default workload measures three runs of 4,000 mutations with eight concurrent
callers for each durability policy. Calls go through the proxy and return only
after their policy's acknowledgment. Worker creation/join is included; open and
close are excluded. The domain increments a counter. Group commit uses its
opt-in 1 ms window; the baseline synchronizes every call.

Restore replays a real one-million-record deterministic journal fixture, from
an empty checkpoint, once per invocation. Fixture construction is outside the
timed interval and uses distinct Action/argument/result containers with fixed
timestamps. Recovery validates the final counter and includes opening the new
journal. This is warm-cache recovery, not a cold-cache storage throughput test.
The single-caller runs use only 10,000 restore actions; their normalized values
must not be mistaken for million-action measurements.

Snapshot timing uses 64 MiB of distinct 1 KiB byte objects added to the restored
domain, three blocking snapshots, no compression or HMAC. The pause is elapsed
time inside ``take_snapshot`` (the domain-lock interval), not an external
request-latency percentile. For supported single-threaded POSIX configurations,
``--fork`` instead measures the parent pause through fork separately from total
time through ``job.wait()``. Check ``fork_jobs`` in the JSON: zero means no fork
was measured, including a platform fallback. Do not report fallback as fork
performance.

Local results, 2026-10-10
----------------------------

Python 3.12.2, macOS 27.0.1 arm64, eight logical CPUs, system temporary directory
on the local APFS volume, ``TZ=UTC``. The process ran under the development
sandbox, on a shared interactive host. Raw samples, parameters and medians are
checked in under ``benchmarks/f18-{before,after}{,-single}.json``. These are
observations from one sequence of runs, not statistically established gains.

.. list-table:: Before and after (write/snapshot medians; one full restore each)
   :header-rows: 1
   :widths: 50 25 25

   * - Measurement
     - Before
     - After (1 ms batching)
   * - Buffered writes/second, 8 callers
     - 4,270
     - 6,165
   * - Sync writes/second, 8 callers
     - 3,235
     - 3,751
   * - Restore seconds, 1,000,000 actions
     - 9.878
     - 11.638
   * - Blocking snapshot pause, 64 MiB (ms)
     - 80.722
     - 78.920
   * - Buffered writes/second, 1 caller
     - 6,757
     - 7,495
   * - Sync writes/second, 1 caller
     - 4,986
     - 557

The concurrent sync median increased in this run, but the individual samples
vary widely and do not establish a general gain. Buffered writes and blocking
snapshots did not receive a comparable algorithmic optimization; their
differences illustrate host/cache variability. Restore was slower in this run.
Single-caller sync throughput fell substantially with batching enabled. For
that reason, the shipping default remains immediate sync
(``group_commit_delay=0``); the after measurements explicitly enable batching.
The two million-action runs are separate fixtures with identical construction,
and no cold-cache or power-loss claims follow from these measurements.

There are no published Linux fork pause measurements yet. The production API
falls back on this macOS host, and no Linux runtime was available. Run the
Linux CI matrix and repeat blocking/fork benchmarks on supported deployment
hardware before making a fork performance claim. Compression round trips and
corruption rejection are tested, but compression speed/ratio are not benchmarked
here; measure them with representative application state. Signed/compressed
snapshots currently require whole payloads in memory.

Validation scope
----------------

Tests gate batch acknowledgment on actual synchronization, inject append/sync/
rotation faults, interleave snapshots with concurrent writes, and check exact
replay ordering. Compression tests cover both extras, pickle/JSON, signed and
unsigned state, old uncompressed snapshots, corruption, and authentication
before decoding. CI installs both extras on Linux and macOS.

Fork integration tests run fresh single-threaded subprocesses. Linux CI uses
the public eligibility check. For local mechanism testing only,
``COOPY_TEST_FORK_INTERNAL=1 python -m pytest tests/functional/test_fork_snapshot.py``
allows those pristine test subprocesses to bypass the macOS gate. This tests
copy-on-write boundaries, child failures, timeout/reaping and publication, not
arbitrary macOS/native-library safety. The public API never reads that test
environment variable. Native Linux validation and power-loss testing remain
outside the local evidence.
