"""Run with: python docs/examples/state_migration.py"""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from address_book import AddressBook, split_name

import coopy
from coopy.base import init_persistent_system

# Written by the first release of address_book; never opened in place.
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "address_book_v1"


def upgrade_add(args, kwargs):
    # Journal records of add(name, phone) replay as add(first, last, phone).
    name, phone = args
    return (*split_name(name), phone), kwargs


def open_book(directory):
    schemas = coopy.ActionSchemas({"add": 2})
    schemas.register("add", 1, upgrade_add)
    return init_persistent_system(AddressBook, basedir=directory, schemas=schemas)


def migrate(directory):
    book = open_book(directory)
    try:
        # From the version 1 snapshot, upgraded by Contact.__setstate__.
        assert book.describe("Ada Lovelace") == {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "telephone": "555-0100",
            "email": None,
        }
        assert book.describe("Alan Turing")["telephone"] == "555-0101"
        # From the journal after that snapshot, upgraded by the action upcaster.
        assert book.describe("Grace Hopper")["last_name"] == "Hopper"
        book.add("Katherine", "Johnson", "555-0103", email="kj@example.com")
        book.take_snapshot()  # rewrites every contact in the version 4 shape
    finally:
        book.close()

    book = open_book(directory)
    try:
        assert book.describe("Ada Lovelace")["first_name"] == "Ada"
        assert book.describe("Katherine Johnson")["email"] == "kj@example.com"
    finally:
        book.close()


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        data = Path(directory) / "data"
        shutil.copytree(FIXTURE, data)
        migrate(data)
