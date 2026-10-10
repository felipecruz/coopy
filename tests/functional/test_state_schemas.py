"""Registered snapshot-state upgraders (StateSchemas) against 0.6.0 fixtures."""

import pickle
import shutil
from pathlib import Path

import pytest

import coopy
from coopy.foundation import VersionedState
from coopy.restore import RecoveryError
from tests import state_domain
from tests.state_domain import TodoList, rename_items, strings_to_dicts

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "state" / "todo_v1"


def schemas(*, skip=None):
    result = coopy.StateSchemas()
    for version, upgrade in ((1, strings_to_dicts), (2, rename_items)):
        if version != skip:
            result.register(TodoList, from_version=version, upgrade=upgrade)
    return result


@pytest.fixture
def data(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "data")
    return tmp_path / "data"


def latest_snapshot(directory):
    return pickle.loads(max(Path(directory).glob("snapshot_*.dat")).read_bytes())


def test_fixture_holds_unversioned_0_6_0_state():
    stored = latest_snapshot(FIXTURE)
    assert type(stored) is TodoList and stored.items == ["write docs", "ship"]
    assert not hasattr(stored, "tasks")
    assert b'coopy_version": "0.6.0' in (FIXTURE / "coopy.json").read_bytes()


def test_0_6_0_fixture_upgrades_across_versions_then_replays(data):
    with coopy.open(TodoList, data, state_schemas=schemas()) as todo:
        assert todo.title == "Todo"
        # Snapshot upgraded 1 -> 2 -> 3 before the later journal replayed add().
        assert [task["text"] for task in todo.tasks] == ["write docs", "ship", "celebrate"]
        assert not hasattr(todo, "items")
        todo.complete("ship")
        coopy.control(todo).take_snapshot()

    stored = latest_snapshot(data)
    assert type(stored) is VersionedState and stored.version == 3
    assert stored.state.tasks[1] == {"text": "ship", "done": True}
    # Current snapshots need no upgraders.
    with coopy.open(TodoList, data) as todo:
        assert todo.tasks[1]["done"] is True


def test_strict_recovery_fails_on_missing_upgrader(data):
    with pytest.raises(RecoveryError, match="Missing state upgrader for TodoList version 2"):
        coopy.open(TodoList, data, state_schemas=schemas(skip=2))
    with pytest.raises(RecoveryError, match="version 1"):
        coopy.open(TodoList, data)


def test_salvage_reports_missing_upgrader_without_writing(data):
    before = sorted(path.name for path in data.iterdir())
    result = coopy.open(TodoList, data, recovery="salvage", state_schemas=schemas(skip=1))
    assert result.system is None
    assert result.report.stop.kind == "checkpoint"
    assert "Missing state upgrader for TodoList version 1" in result.report.stop.detail
    assert sorted(path.name for path in data.iterdir()) == before


def test_newer_or_invalid_stored_version_fails(tmp_path, monkeypatch):
    with coopy.open(TodoList, tmp_path) as todo:
        todo.add("x")
        coopy.control(todo).take_snapshot()
    monkeypatch.setattr(TodoList, "__coopy_version__", 2)
    with pytest.raises(RecoveryError, match="Unsupported state version for TodoList: 3"):
        coopy.open(TodoList, tmp_path)
    result = coopy.open(TodoList, tmp_path, recovery="salvage")
    assert "Unsupported state version" in result.report.stop.detail


@pytest.mark.parametrize(
    "upgrade, message",
    [(lambda todo: None, "must return a TodoList"), (lambda todo: 1 / 0, "upgrader failed")],
)
def test_invalid_upgrader_stops_recovery(data, upgrade, message):
    state_schemas = schemas(skip=2)
    state_schemas.register(TodoList, 2, upgrade)
    with pytest.raises(RecoveryError, match=message):
        coopy.open(TodoList, data, state_schemas=state_schemas)


@pytest.mark.parametrize("from_version", [0, 3, 4, "1", 1.0])
def test_registration_must_advance_toward_current_version(from_version):
    with pytest.raises(coopy.SerializationError):
        coopy.StateSchemas().register(TodoList, from_version, strings_to_dicts)


def test_registration_is_unique_and_per_class():
    state_schemas = schemas()
    with pytest.raises(coopy.SerializationError):
        state_schemas.register(TodoList, 1, strings_to_dicts)
    with pytest.raises(coopy.SerializationError):
        state_schemas.register(TodoList(), 1, strings_to_dicts)


@pytest.mark.parametrize("version", [0, -1, "3", True])
def test_invalid_declared_version_rejected(tmp_path, monkeypatch, version):
    monkeypatch.setattr(TodoList, "__coopy_version__", version)
    with pytest.raises(coopy.SerializationError, match="positive integer"):
        coopy.open(TodoList, tmp_path)


def test_unversioned_classes_keep_the_0_6_0_layout(tmp_path):
    class Plain:
        def __init__(self):
            self.values = []

    state_domain.Plain = Plain
    Plain.__module__, Plain.__qualname__ = state_domain.__name__, "Plain"
    try:
        coopy.control(coopy.open(Plain, tmp_path)).close()
        assert type(latest_snapshot(tmp_path)) is Plain
    finally:
        del state_domain.Plain


@pytest.mark.parametrize("secret", [None, b"state-secret"])
@pytest.mark.parametrize("compression", [None, "zstd"])
def test_json_signed_and_compressed_snapshots_record_version(
    tmp_path, monkeypatch, secret, compression
):
    if compression:
        pytest.importorskip("zstandard")
    registry = coopy.TypeRegistry()

    def decode(state):
        todo = TodoList.__new__(TodoList)
        todo.__dict__.update(state)
        return todo

    registry.register("todo", TodoList, encode=vars, decode=decode)
    options = dict(
        serializer=coopy.JsonSerializer(registry),
        secret=secret,
        snapshot_compression=compression,
    )
    with coopy.open(TodoList, tmp_path, **options) as todo:
        todo.add("x")
        coopy.control(todo).take_snapshot()
    monkeypatch.setattr(TodoList, "__coopy_version__", 4)
    state_schemas = coopy.StateSchemas()
    state_schemas.register(TodoList, 3, lambda todo: setattr(todo, "title", "v4") or todo)
    with coopy.open(TodoList, tmp_path, state_schemas=state_schemas, **options) as todo:
        assert todo.title == "v4" and todo.tasks[0]["text"] == "x"
