"""Check a wheel-installed public API outside the source checkout."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    destination = Path(directory)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps',
                    '--no-build-isolation', '--target', str(destination), str(root)], check=True)
    assert (destination / 'coopy' / 'py.typed').is_file()
    example = destination / 'public_api.py'
    example.write_bytes((root / 'tests/typing/public_api.py').read_bytes())
    env = os.environ.copy()
    env['MYPYPATH'] = directory
    subprocess.run([sys.executable, '-m', 'mypy', '--strict', '--follow-imports=silent',
                    '--python-version=3.10', str(example)], cwd=directory, env=env, check=True)
