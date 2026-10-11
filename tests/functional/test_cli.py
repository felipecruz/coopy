"""F30: ``python -m coopy`` against fixtures; every command honors the writer lock."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import coopy
from coopy import fileutils
from coopy.cli import TRUST_NOTICE, count_records, duration, main
from coopy.manifest import MANIFEST_FILE

from .test_serialization import Tasks, json_serializer

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
TASKS = "tests.functional.test_serialization:Tasks"
JSON = "tests.functional.test_serialization:json_serializer"
STATE_SCHEMAS = "tests.functional.test_state_schemas:schemas"
SECRET = "test-only-cli-secret"
OTHER = "test-only-cli-other"


@pytest.fixture
def legacy(tmp_path):
    shutil.copytree(FIXTURES / "legacy" / "v0_5", tmp_path / "legacy")
    return tmp_path / "legacy"


@pytest.fixture
def todo(tmp_path):
    shutil.copytree(FIXTURES / "state" / "todo_v1", tmp_path / "todo")
    return tmp_path / "todo"


@pytest.fixture
def secrets(monkeypatch):
    monkeypatch.setenv("COOPY_SECRET", SECRET)
    monkeypatch.setenv("COOPY_OTHER", OTHER)


def populate(directory, **options):
    with coopy.open(Tasks, directory, **options) as tasks:
        tasks.add("checkpoint", 1)
        coopy.control(tasks).take_snapshot()
        tasks.add("journal", 2)
        tasks.timed("clock")
        with pytest.raises(ValueError, match="expected"):
            tasks.fail("failure")
        return tasks.items[:]


def run(capsys, *argv):
    code = main([str(arg) for arg in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def storage(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir() if p.name != "coopy.lock"}


def test_inspect_legacy_fixture_decodes_nothing(capsys, legacy):
    code, out, err = run(capsys, "inspect", legacy)
    assert code == 0 and not err
    assert "format: 0 (legacy" in out
    assert "checkpoint: snapshot_000000000000004.dat" in out
    assert "transaction_000000000000003.log  218 bytes  actions: 1, before checkpoint" in out
    assert "actions replayed on open: 1" in out
    assert "actions before the checkpoint: 1" in out


@pytest.mark.parametrize("kind", ["pickle", "json", "signed"])
def test_inspect_counts_each_storage_format(capsys, tmp_path, kind, secrets):
    options = {
        "pickle": {},
        "json": {"serializer": json_serializer()},
        "signed": {"secret": SECRET.encode()},
    }[kind]
    with coopy.open(Tasks, tmp_path, **options) as tasks:
        tasks.add("one")
        coopy.control(tasks).take_snapshot()
        tasks.add("two")
        tasks.add("three")
    code, out, _ = run(capsys, "inspect", tmp_path)
    assert code == 0
    assert "actions replayed on open: 2" in out
    assert "actions before the checkpoint: 1" in out
    assert f"serializer: {'json' if kind == 'json' else 'pickle'}" in out
    assert ("signed (counted from envelopes" in out) is (kind == "signed")


def test_inspect_reports_damaged_journal(capsys, legacy):
    journal = legacy / "transaction_000000000000006.log"
    journal.write_bytes(journal.read_bytes()[:-5])
    code, out, _ = run(capsys, "inspect", legacy)
    assert code == 1 and "DAMAGED" in out


def test_count_records_rejects_truncation(tmp_path):
    path = tmp_path / "transaction_000000000000002.log"
    path.write_bytes(b'{"a"}\n{"b"')
    with pytest.raises(ValueError, match="truncated JSON"):
        count_records(path, "json", signed=False)
    path.write_bytes(b"COOPY")
    with pytest.raises(ValueError, match="signed"):
        count_records(path, "pickle", signed=True)
    assert count_records(path, "custom:x.Y", signed=False) is None


def test_verify_states_trust_and_succeeds(capsys, legacy):
    before = storage(legacy)
    code, out, err = run(capsys, "verify", legacy)
    assert code == 0 and "OK: strict recovery succeeded" in out
    assert "actions replayed: 1" in out
    assert TRUST_NOTICE in err
    assert storage(legacy) == before


def test_verify_uses_state_schemas(capsys, todo):
    code, _, err = run(capsys, "verify", todo)
    assert code == 1 and "Missing state upgrader" in err
    code, out, _ = run(capsys, "verify", todo, "--state-schemas", STATE_SCHEMAS)
    assert code == 0 and "actions replayed: 1" in out


def test_verify_fails_on_corruption(capsys, legacy):
    journal = legacy / "transaction_000000000000006.log"
    journal.write_bytes(journal.read_bytes()[:-5])
    code, _, err = run(capsys, "verify", legacy)
    assert code == 1 and "RecoveryError" in err and "decode" in err


def test_verify_signed_requires_the_secret(capsys, tmp_path, secrets):
    populate(tmp_path, secret=SECRET.encode())
    code, _, err = run(capsys, "verify", tmp_path)
    assert code == 1 and "HMAC-signed" in err
    code, _, err = run(capsys, "verify", tmp_path, "--secret-env", "COOPY_OTHER")
    assert code == 1 and "verification" in err
    code, out, _ = run(
        capsys, "verify", tmp_path, "--secret-env", "COOPY_OTHER", "--secret-env", "COOPY_SECRET"
    )
    assert code == 0 and "expected failures replayed: 1" in out
    code, _, err = run(capsys, "verify", tmp_path, "--secret-env", "COOPY_UNSET")
    assert code == 1 and "COOPY_UNSET" in err


def test_log_lists_actions_with_arguments_times_and_outcomes(capsys, tmp_path):
    populate(tmp_path)
    code, out, err = run(capsys, "log", tmp_path)
    assert code == 0 and TRUST_NOTICE in err
    lines = out.splitlines()
    assert any(
        line.startswith("== transaction_") and "before the checkpoint" in line for line in lines
    )
    assert any("add('checkpoint', 1)" in line for line in lines)
    assert any("add('journal', 2)" in line for line in lines)
    timed = next(line for line in lines if "timed('clock')" in line)
    assert "clock=[" in timed
    assert "[raised]" in next(line for line in lines if "fail('failure')" in line)

    code, out, _ = run(capsys, "log", tmp_path, "--after-checkpoint")
    assert code == 0 and "checkpoint', 1" not in out and "journal', 2" in out


def test_log_json_and_signed(capsys, tmp_path, secrets):
    populate(tmp_path / "json", serializer=json_serializer())
    code, out, _ = run(capsys, "log", tmp_path / "json", "--serializer", "json")
    assert code == 0 and "add('journal', 2)" in out
    code, _, err = run(capsys, "log", tmp_path / "json")
    assert code == 1 and "serializer" in err

    populate(tmp_path / "signed", secret=SECRET.encode())
    code, out, _ = run(capsys, "log", tmp_path / "signed", "--secret-env", "COOPY_SECRET")
    assert code == 0 and "add('journal', 2)" in out
    journal = max((tmp_path / "signed").glob("transaction_*.log"))
    data = bytearray(journal.read_bytes())
    data[-1] ^= 1
    journal.write_bytes(bytes(data))
    code, _, err = run(capsys, "log", tmp_path / "signed", "--secret-env", "COOPY_SECRET")
    assert code == 1 and "HMAC verification failed" in err


def test_log_truncates_long_arguments(capsys, tmp_path):
    with coopy.open(Tasks, tmp_path) as tasks:
        tasks.add("x" * 500, list(range(100)))
    code, out, _ = run(capsys, "log", tmp_path)
    line = next(line for line in out.splitlines() if "add(" in line)
    assert code == 0 and len(line) < 200 and "..." in line


def test_snapshot_writes_a_new_checkpoint(capsys, tmp_path):
    expected = populate(tmp_path)
    before = fileutils.list_snapshot_files(tmp_path)
    code, out, err = run(capsys, "snapshot", tmp_path, TASKS)
    assert code == 0 and TRUST_NOTICE in err and "replayed 3 actions" in out
    after = fileutils.list_snapshot_files(tmp_path)
    assert len(after) == len(before) + 1 and after[-1] in out
    with coopy.open(Tasks, tmp_path) as reopened:
        assert reopened.items == expected
        assert coopy.control(reopened).recovery_report.replayed == 0


def test_snapshot_with_json_factory_and_errors(capsys, tmp_path, secrets):
    expected = populate(tmp_path, serializer=json_serializer())
    code, _, _ = run(capsys, "snapshot", tmp_path, TASKS, "--serializer", JSON)
    assert code == 0
    with coopy.open(Tasks, tmp_path, serializer=json_serializer()) as reopened:
        assert reopened.items == expected
    assert run(capsys, "snapshot", tmp_path, "tests.nothing:Tasks")[0] == 1
    assert "not a class" in run(capsys, "snapshot", tmp_path, JSON)[2]
    assert "module:name" in run(capsys, "snapshot", tmp_path, "Tasks")[2]
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / MANIFEST_FILE).write_text(json.dumps({"format_version": 1}))
    code, _, err = run(capsys, "snapshot", empty, TASKS)
    assert code == 1 and "no checkpoint" in err
    assert not fileutils.list_snapshot_files(empty)


def test_prune_command(capsys, tmp_path):
    with coopy.open(Tasks, tmp_path) as tasks:
        for index in range(4):
            tasks.add("item", index)
            coopy.control(tasks).take_snapshot()
        expected = tasks.items[:]
    code, out, err = run(capsys, "prune", tmp_path, "--keep", 2)
    assert code == 0 and not err
    assert "removed 3 checkpoints" in out and "kept 2 checkpoints" in out
    assert len(fileutils.list_snapshot_files(tmp_path)) == 2
    code, out, _ = run(capsys, "prune", tmp_path, "--keep", 1, "--keep-for", "1d")
    assert code == 0 and "removed 0 checkpoints" in out
    with coopy.open(Tasks, tmp_path) as reopened:
        assert reopened.items == expected


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_prune_rejects_bad_keep(capsys, tmp_path, value):
    with pytest.raises(SystemExit) as exit:
        main(["prune", str(tmp_path), "--keep", value])
    assert exit.value.code == 2


def test_duration():
    assert duration("90") == duration("90s") == duration("1.5m")
    assert duration("2w").days == 14 and duration("12h").seconds == 43200
    with pytest.raises(Exception):
        duration("soon")


def test_convert_command(capsys, tmp_path, secrets):
    expected = populate(tmp_path / "src")
    before = storage(tmp_path / "src")
    code, out, err = run(
        capsys, "convert", tmp_path / "src", tmp_path / "dst", "--to-serializer", JSON,
        "--to-secret-env", "COOPY_SECRET",
    )  # fmt: skip
    assert code == 0 and TRUST_NOTICE in err and "actions replayed: 3" in out
    assert storage(tmp_path / "src") == before
    with coopy.open(
        Tasks, tmp_path / "dst", serializer=json_serializer(), secret=SECRET.encode()
    ) as converted:
        assert converted.items == expected
    code, _, _ = run(
        capsys, "convert", tmp_path / "dst", tmp_path / "back", "--serializer", JSON,
        "--secret-env", "COOPY_SECRET", "--to-serializer", "pickle", "--unsigned",
    )  # fmt: skip
    assert code == 0
    with coopy.open(Tasks, tmp_path / "back") as back:
        assert back.items == expected
    code, _, err = run(capsys, "convert", tmp_path / "src", tmp_path / "back")
    assert code == 1 and "not empty" in err


@pytest.mark.parametrize(
    "argv",
    [
        ["inspect", "{d}"],
        ["verify", "{d}"],
        ["log", "{d}"],
        ["snapshot", "{d}", TASKS],
        ["prune", "{d}", "--keep", "1"],
        ["convert", "{d}", "{d}-copy"],
    ],
)
def test_every_command_honors_the_writer_lock(capsys, tmp_path, argv):
    directory = tmp_path / "data"
    populate(directory)
    before = storage(directory)
    with coopy.open(Tasks, directory) as tasks:
        tasks.add("open", 0)
        before = storage(directory)
        code, _, err = run(capsys, *[arg.format(d=directory) for arg in argv])
        assert code == 1 and "already open for writing" in err
        assert storage(directory) == before
    assert not (tmp_path / "data-copy").exists()


@pytest.mark.parametrize("command", ["inspect", "verify", "log", "snapshot", "prune", "convert"])
def test_missing_or_foreign_directories_fail(capsys, tmp_path, command):
    extra = {"snapshot": [TASKS], "prune": ["--keep", "1"], "convert": [tmp_path / "out"]}
    for target in (tmp_path / "missing", tmp_path):
        code, _, err = run(capsys, command, target, *extra.get(command, []))
        assert code == 1 and "coopy: error:" in err
    assert not (tmp_path / "coopy.lock").exists()


def test_python_dash_m_entry_point_and_help(tmp_path):
    shutil.copytree(FIXTURES / "legacy" / "v0_5", tmp_path / "legacy")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    def coopy_cli(*argv):
        return subprocess.run(
            [sys.executable, "-m", "coopy", *map(str, argv)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    result = coopy_cli("verify", tmp_path / "legacy")
    assert result.returncode == 0 and "OK" in result.stdout
    assert "unpickles" in result.stderr and "PYTHONPATH" in result.stderr
    assert coopy_cli("verify", tmp_path / "missing").returncode == 1
    assert coopy_cli().returncode == 2
    for command in ("verify", "log", "snapshot", "convert"):
        help_text = " ".join(coopy_cli(command, "--help").stdout.split())
        assert "unpickles" in help_text and "PYTHONPATH" in help_text
