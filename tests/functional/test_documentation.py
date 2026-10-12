"""Execute the exact Python sources included by the Sphinx guide."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "docs" / "examples"


def run_example(tmp_path, *arguments):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(EXAMPLES)))
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", *arguments],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "example",
    [
        "quickstart.py",
        "persistence.py",
        "decorator_semantics.py",
        "replication.py",
        "state_migration.py",
        "raffle.py",
    ],
)
def test_documented_example(tmp_path, example):
    # The example owns its temporary data directory; logs stay in the temporary working directory.
    run_example(tmp_path, str(EXAMPLES / example))


def test_tutorial_domain_recovers_in_another_process(tmp_path):
    run_example(
        tmp_path,
        "-c",
        """
import json
from pathlib import Path
from coopy.base import init_persistent_system
from wiki import Wiki
wiki = init_persistent_system(Wiki, basedir="data")
try:
    wiki.create_page("Home", "checkpoint")
    wiki.take_snapshot()
    wiki.create_page("Journal", "replay")
    Path("expected.json").write_text(json.dumps(wiki.get_page("Journal"), default=str))
finally:
    wiki.close()
""",
    )
    run_example(
        tmp_path,
        "-c",
        """
import json
from pathlib import Path
from coopy.base import init_persistent_system
from wiki import Wiki
wiki = init_persistent_system(Wiki(), basedir="data")
try:
    assert wiki.get_page("Home")["content"] == "checkpoint"
    actual = json.dumps(wiki.get_page("Journal"), default=str)
    assert actual == Path("expected.json").read_text()
finally:
    wiki.close()
""",
    )


STATE_FIXTURE = EXAMPLES / "fixtures" / "address_book_v1"


def test_state_migration_fixture_holds_version_1_state():
    # Guards the fixture: it must keep the old shape the example upgrades.
    snapshot = max(STATE_FIXTURE.glob("snapshot_*.dat")).read_bytes()
    assert b"phone" in snapshot and b"name" in snapshot
    assert b"state_version" not in snapshot and b"telephone" not in snapshot


def test_state_migration_rewrites_snapshot_and_rejects_newer_state(tmp_path):
    run_example(
        tmp_path,
        "-c",
        f"""
import pickle
import shutil
from pathlib import Path
import state_migration
from address_book import Contact
shutil.copytree({str(STATE_FIXTURE)!r}, "data")
state_migration.migrate("data")
latest = max(Path("data").glob("snapshot_*.dat"))
book = pickle.loads(latest.read_bytes())
contact = book.contacts["Ada Lovelace"]
assert contact.__getstate__()["state_version"] == 4
assert b"state_version" in latest.read_bytes()
newer = Contact.__new__(Contact)
try:
    newer.__setstate__({{"state_version": 5}})
except ValueError as error:
    assert "newer" in str(error)
else:
    raise AssertionError("newer state accepted")
""",
    )
