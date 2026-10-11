"""Decorator outcomes in real journals and after a fresh-process restart."""

import pickle
import subprocess
import sys

import pytest

from coopy.base import init_persistent_system
from coopy.decorators import abort_exception, readonly


class Ledger:
    def __init__(self):
        self.entries = []

    def add(self, value, *, fail=False):
        entry = (value, self._clock.now())
        self.entries.append(entry)
        if fail:
            raise ValueError("rejected")
        return entry

    @abort_exception
    def add_or_abort(self, value, *, fail=False):
        return self.add(value, fail=fail)

    @readonly
    @abort_exception
    def read(self, *, fail=False):
        if fail:
            raise ValueError("rejected query")
        return list(self.entries)

    @abort_exception
    @readonly
    def read_reverse_order(self, *, fail=False):
        return self.read(fail=fail)


def test_abort_outcomes_survive_process_restart(tmp_path):
    ledger = init_persistent_system(Ledger, basedir=str(tmp_path))
    try:
        first = ledger.add_or_abort("success")
        with pytest.raises(ValueError, match="^rejected$"):
            ledger.add_or_abort("omitted", fail=True)
        with pytest.raises(ValueError, match="^rejected$"):
            ledger.add("ordinary failure", fail=True)
        last = ledger.add_or_abort("after failures")
        # Aborting the journal entry does not undo the live mutation.
        assert [entry[0] for entry in ledger.entries] == [
            "success",
            "omitted",
            "ordinary failure",
            "after failures",
        ]
        expected = [first, ledger.entries[2], last]
        for query in (ledger.read, ledger.read_reverse_order):
            assert query() == ledger.entries
            with pytest.raises(ValueError, match="^rejected query$"):
                query(fail=True)
    finally:
        ledger.close()

    actions = []
    for path in sorted(tmp_path.glob("transaction_*.log")):
        with path.open("rb") as stream:
            unpickler = pickle.Unpickler(stream)
            while True:
                try:
                    actions.append(unpickler.load())
                except EOFError:
                    break
    assert [action.action for action in actions] == ["add_or_abort", "add", "add_or_abort"]
    assert [action.raised for action in actions] == [False, True, False]
    assert [action.results for action in actions] == [[("now", entry[1])] for entry in expected]

    expected_path = tmp_path / "expected.pkl"
    expected_path.write_bytes(pickle.dumps(expected))
    script = """
import pickle, sys
from coopy.base import init_persistent_system
from tests.functional.test_abort_exception import Ledger
ledger = init_persistent_system(Ledger, basedir=sys.argv[1])
try:
    with open(sys.argv[2], 'rb') as stream:
        expected = pickle.load(stream)
    assert ledger.read() == expected, (ledger.read(), expected)
finally:
    ledger.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), str(expected_path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_snapshot_can_preserve_mutation_from_aborted_call(tmp_path):
    ledger = init_persistent_system(Ledger, basedir=str(tmp_path))
    try:
        with pytest.raises(ValueError, match="^rejected$"):
            ledger.add_or_abort("still in memory", fail=True)
        ledger.take_snapshot()
    finally:
        ledger.close()
    ledger = init_persistent_system(Ledger, basedir=str(tmp_path))
    try:
        assert [entry[0] for entry in ledger.read()] == ["still in memory"]
    finally:
        ledger.close()
