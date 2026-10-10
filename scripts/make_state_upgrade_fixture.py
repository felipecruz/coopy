"""Regenerate tests/fixtures/state/todo_v1.

Records the first, unversioned release of ``tests.state_domain.TodoList``
(``items`` holds plain strings) to a snapshot and a later journal, the way
coopy 0.6.0 wrote them. Unversioned classes are stored unchanged since 0.6.0,
so this keeps producing 0.6.0 files. Run from a source checkout:

    python scripts/make_state_upgrade_fixture.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tests" / "fixtures" / "state" / "todo_v1"

RECORD = """
import sys
import types

import tests

VERSION_1 = '''
class TodoList:
    def __init__(self):
        self.items = []

    def add(self, text):
        self.items.append(text)
'''
# Pickle records the module path the tests import the current class from.
module = types.ModuleType("tests.state_domain")
exec(VERSION_1, module.__dict__)
sys.modules["tests.state_domain"] = tests.state_domain = module

from coopy.base import init_persistent_system

todo = init_persistent_system(module.TodoList, basedir="data")
try:
    todo.add("write docs")
    todo.add("ship")
    todo.take_snapshot()
    todo.add("celebrate")
finally:
    todo.close()
"""


def main():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        subprocess.run(
            [sys.executable, "-c", RECORD], cwd=work, env={"PYTHONPATH": str(ROOT)}, check=True
        )
        shutil.rmtree(TARGET, ignore_errors=True)
        shutil.copytree(work / "data", TARGET, ignore=shutil.ignore_patterns("coopy.lock"))
    print(sorted(path.name for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
