"""Run with: python docs/examples/decorator_semantics.py"""

from tempfile import TemporaryDirectory

from coopy.base import init_persistent_system
from coopy.decorators import abort_exception, readonly


class Ledger:
    def __init__(self):
        self.entries = []

    def add(self, value, fail=False):
        self.entries.append(value)
        if fail:
            raise ValueError("rejected after mutation")

    @abort_exception
    def add_or_abort(self, value, fail=False):
        # Deliberately unsafe to demonstrate that abort is not rollback.
        self.add(value, fail=fail)

    @readonly
    def read(self):
        return tuple(self.entries)


def demonstrate(directory):
    ledger = init_persistent_system(Ledger, basedir=directory)
    try:
        ledger.add_or_abort("success")
        for method, value in (
            (ledger.add, "ordinary failure"),
            (ledger.add_or_abort, "omitted failure"),
        ):
            try:
                method(value, fail=True)
            except ValueError:
                pass
            else:
                raise AssertionError("Expected the domain exception")
        assert ledger.read() == ("success", "ordinary failure", "omitted failure")
        # No snapshot here: it would retain the omitted in-memory mutation.
    finally:
        ledger.close()

    ledger = init_persistent_system(Ledger, basedir=directory)
    try:
        assert ledger.read() == ("success", "ordinary failure")
    finally:
        ledger.close()


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        demonstrate(directory)
