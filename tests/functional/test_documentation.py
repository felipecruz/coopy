"""Execute the exact Python sources included by the Sphinx guide."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "docs" / "examples"


def run_example(tmp_path, *arguments):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(EXAMPLES)))
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", *arguments],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("example", [
    "persistence.py", "decorator_semantics.py", "replication.py",
])
def test_documented_example(tmp_path, example):
    # The example owns its temporary data directory; logs stay in the temporary working directory.
    run_example(tmp_path, str(EXAMPLES / example))


def test_tutorial_domain_recovers_in_another_process(tmp_path):
    run_example(tmp_path, "-c", '''
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
''')
    run_example(tmp_path, "-c", '''
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
''')
