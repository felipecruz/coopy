"""Reproducible local persistence measurements (no third-party dependencies)."""

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

# Run this same script against an old checkout by setting PYTHONPATH explicitly.
from coopy.base import control, init_persistent_system
from coopy.foundation import Action


class Counter:
    def __init__(self):
        self.value = 0
        self.payload = []

    def add(self, value):
        self.value += value


def measure(args):
    results = {}
    with tempfile.TemporaryDirectory(dir=args.directory) as root:
        for mode in ("buffered", "sync"):
            samples = []
            for run in range(args.repeats):
                options = (
                    {}
                    if args.group_commit_delay is None
                    else {"group_commit_delay": args.group_commit_delay}
                )
                proxy = init_persistent_system(
                    Counter, Path(root) / f"{mode}-{run}", durability=mode, **options
                )

                def write(worker):
                    for _ in range(worker, args.writes, args.workers):
                        proxy.add(1)

                start = time.perf_counter()
                with ThreadPoolExecutor(args.workers) as pool:
                    list(pool.map(write, range(args.workers)))
                samples.append(args.writes / (time.perf_counter() - start))
                assert proxy.value == args.writes
                control(proxy).close()
            results[mode + "_writes_per_second"] = samples
        directory = Path(root) / "restore"
        proxy = init_persistent_system(Counter, directory)
        # Build a deterministic journal fixture outside the measured interval.
        # Distinct records/containers match normal journaling without spending
        # setup time converting a million wall-clock timestamps to local time.
        journal = proxy.publisher.subscribers[0]
        for _ in range(args.actions):
            action = Action(1, "add", datetime(2026, 1, 1), tuple([1]), {})
            action.results = []
            action.raised = False
            journal.receive(action)
        control(proxy).close()
        start = time.perf_counter()
        proxy = init_persistent_system(Counter, directory)
        elapsed = time.perf_counter() - start
        assert proxy.value == args.actions
        results["restore_actions"] = args.actions
        results["restore_seconds"] = elapsed
        results["restore_seconds_per_million"] = elapsed * 1_000_000 / args.actions
        # Distinct objects avoid measuring only pickle memo reuse.
        proxy.obj.payload = [bytes([i % 256]) * 1024 for i in range(args.snapshot_mib * 1024)]
        pauses, totals = [], []
        fork_jobs = 0
        for _ in range(args.repeats):
            start = time.perf_counter()
            if args.fork:
                job = control(proxy).take_snapshot(mode="fork", fork_safe=True)
            else:
                job = control(proxy).take_snapshot()
            pauses.append(time.perf_counter() - start)
            if job is not None:
                fork_jobs += 1
                job.wait()
            totals.append(time.perf_counter() - start)
        results["snapshot_pause_seconds"] = pauses
        results["snapshot_total_seconds"] = totals
        results["fork_jobs"] = fork_jobs
        control(proxy).close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writes", type=int, default=4000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--actions", type=int, default=1_000_000)
    parser.add_argument("--snapshot-mib", type=int, default=64)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--directory", default=None)
    parser.add_argument("--fork", action="store_true")
    parser.add_argument("--group-commit-delay", type=float, default=None)
    args = parser.parse_args()
    result = {
        "python": sys.version,
        "platform": platform.platform(),
        "timezone": os.environ.get("TZ"),
        "cpu_count": os.cpu_count(),
        "parameters": vars(args),
        "measurements": measure(args),
    }
    result["medians"] = {
        k: statistics.median(v) for k, v in result["measurements"].items() if isinstance(v, list)
    }
    print(json.dumps(result, indent=2))
