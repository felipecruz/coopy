"""Check built metadata and isolated installs: python scripts/check_distributions.py.

Run `python -m build` and `python -m twine check --strict dist/*` first.
Only the standard library is needed; pip fetches the sdist's build requirements.
Each installed artifact writes and restores state in separate Python processes.
"""

import email.policy
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from email.parser import Parser
from pathlib import Path


class Notebook:
    def __init__(self):
        self.entries = []

    def add(self, text):
        self.entries.append(text)


def persistence_round_trip(*, restore):
    import coopy
    from coopy.base import init_persistent_system

    # Isolated Python must load the installed artifact, never the source tree.
    assert Path(coopy.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    notebook = init_persistent_system(Notebook, basedir="data")
    try:
        if restore:
            assert notebook.entries == ["before checkpoint", "after checkpoint"]
        else:
            assert notebook.entries == [], "Round trip must start with fresh storage"
            notebook.add("before checkpoint")
            notebook.take_snapshot()
            notebook.add("after checkpoint")
    finally:
        notebook.close()
    phase = "restored" if restore else "written"
    print(f"Persistence state {phase}: {coopy.__file__}", flush=True)


def check_metadata(raw, readme):
    metadata = Parser(policy=email.policy.default).parsestr(raw.decode("utf-8"))
    assert metadata["Name"] == "coopy"
    assert metadata["Description-Content-Type"] == "text/markdown"
    assert metadata.get_payload().rstrip("\n") == readme.rstrip("\n"), (
        "Distribution description does not match README.md"
    )


def check_distributions():
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    dist = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "dist"
    sdists = list(dist.glob("coopy-*.tar.gz"))
    wheels = list(dist.glob("coopy-*.whl"))
    assert len(sdists) == len(wheels) == 1, "Expected one sdist and one wheel"

    with tarfile.open(sdists[0]) as archive:
        # Check the top-level metadata, not the egg-info copy.
        metadata_files = [
            name
            for name in archive.getnames()
            if name.count("/") == 1 and name.endswith("/PKG-INFO")
        ]
        assert len(metadata_files) == 1
        metadata_path = metadata_files[0]
        check_metadata(archive.extractfile(metadata_path).read(), readme)
        readme_path = metadata_path.rsplit("/", 1)[0] + "/README.md"
        assert archive.extractfile(readme_path).read() == (root / "README.md").read_bytes()

    with zipfile.ZipFile(wheels[0]) as archive:
        metadata_files = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        assert len(metadata_files) == 1
        check_metadata(archive.read(metadata_files[0]), readme)
    print("Both distribution descriptions match README.md", flush=True)

    for artifact in [*sdists, *wheels]:
        with tempfile.TemporaryDirectory(prefix="coopy-install-") as directory:
            work = Path(directory)
            environment = work / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / (
                "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
            )
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--no-cache-dir",
                    "--disable-pip-version-check",
                    "--no-deps",
                    str(artifact),
                ],
                cwd=work,
                check=True,
            )
            # A fresh interpreter must recover from disk without any writer state.
            for phase in ("--write-state", "--restore-state"):
                subprocess.run(
                    [str(python), "-I", str(Path(__file__).resolve()), phase],
                    cwd=work,
                    check=True,
                )
            print(f"Installed artifact passed: {artifact.name}", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--write-state"]:
        persistence_round_trip(restore=False)
    elif sys.argv[1:] == ["--restore-state"]:
        persistence_round_trip(restore=True)
    else:
        check_distributions()
