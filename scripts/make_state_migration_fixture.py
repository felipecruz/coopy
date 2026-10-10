"""Regenerate docs/examples/fixtures/address_book_v1.

Writes the first release of ``address_book`` (contacts with ``name`` and
``phone``, ``add(name, phone)``) to a temporary module, records a snapshot and
one later journaled call with it, and copies the data directory into the
documentation fixtures. Run from a source checkout:

    python scripts/make_state_migration_fixture.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "examples" / "fixtures" / "address_book_v1"

VERSION_1 = """
class Contact:
    def __init__(self, name, phone):
        self.name = name
        self.phone = phone


class AddressBook:
    def __init__(self):
        self.contacts = {}

    def add(self, name, phone):
        self.contacts[name] = Contact(name, phone)
"""

RECORD = """
from coopy.base import init_persistent_system
from address_book import AddressBook
book = init_persistent_system(AddressBook, basedir="data")
try:
    book.add("Ada Lovelace", "555-0100")
    book.add("Alan Turing", "555-0101")
    book.take_snapshot()
    book.add("Grace Hopper", "555-0102")
finally:
    book.close()
"""


def main():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        (work / "address_book.py").write_text(VERSION_1)
        subprocess.run(
            [sys.executable, "-c", RECORD],
            cwd=work,
            env={"PYTHONPATH": f"{work}:{ROOT}"},
            check=True,
        )
        shutil.rmtree(TARGET, ignore_errors=True)
        shutil.copytree(work / "data", TARGET, ignore=shutil.ignore_patterns("coopy.lock"))
    print(sorted(path.name for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
