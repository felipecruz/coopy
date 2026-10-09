"""Exercise codecs through real checkpoints, journals, and recovery policies."""

import json
import sys
import types
from datetime import date, datetime

import pytest

import coopy
from coopy.error import PersistenceError
from coopy.foundation import Action
from coopy.restore import RecoveryError


class Tasks:
    def __init__(self):
        self.items = []

    def add(self, text, priority=0):
        self.items.append((text, priority))

    def timed(self, text):
        self.items.append((text, self._clock.now()))

    def fail(self, text):
        self.items.append((text, -1))
        raise ValueError("expected")


def restore_tasks(state):
    result = Tasks()
    result.__dict__.update(state)
    return result


def json_serializer():
    registry = coopy.TypeRegistry()
    registry.register("tasks", Tasks, encode=lambda obj: vars(obj), decode=restore_tasks)
    return coopy.JsonSerializer(registry)


@pytest.mark.parametrize("kind", ["legacy", "pickle", "json"])
@pytest.mark.parametrize("secret", [None, b"test-secret"])
@pytest.mark.parametrize("durability", ["buffered", "sync"])
def test_codecs_checkpoint_rotation_and_replay(tmp_path, kind, secret, durability):
    serializer = {"legacy": None, "pickle": coopy.PickleSerializer(), "json": json_serializer()}[
        kind
    ]
    options = dict(serializer=serializer, secret=secret, durability=durability)
    with coopy.open(Tasks, tmp_path, **options) as tasks:
        tasks.add("checkpoint")
        coopy.control(tasks).take_snapshot()
        tasks.publisher.subscribers[0].file.max_size = 1
        tasks.add("journal", 7)
        tasks.timed("clock")
        with pytest.raises(ValueError, match="expected"):
            tasks.fail("failure")
        expected = tasks.items[:]
    with coopy.open(Tasks(), tmp_path, **options) as restored:
        assert restored.items == expected
        assert coopy.control(restored).recovery_report.expected_failures == 1
        coopy.control(restored).take_snapshot()
    with coopy.open(Tasks, tmp_path, **options) as restored:
        assert restored.items == expected


def test_json_builtin_values():
    serializer = coopy.JsonSerializer()
    value = {
        "text": "é\n",
        "bytes": b"\x00\xff",
        "date": date(2020, 1, 2),
        "datetime": datetime(2020, 1, 2, 3, 4),
        "tuple": (1, None, True),
        1: [2.5, {"nested": "value"}],
    }
    assert serializer.loads(serializer.dumps(value)) == value


@pytest.mark.parametrize("value", [object(), float("nan"), float("inf")])
def test_json_rejects_unregistered_or_invalid_values(value):
    with pytest.raises(coopy.SerializationError):
        coopy.JsonSerializer().dumps(value)


def test_json_rejects_cycles_and_shared_objects():
    child = []
    with pytest.raises(coopy.SerializationError, match="trees"):
        coopy.JsonSerializer().dumps([child, child])
    child.append(child)
    with pytest.raises(coopy.SerializationError, match="trees"):
        coopy.JsonSerializer().dumps(child)


def test_json_never_falls_back_to_pickle(tmp_path):
    with coopy.open(Tasks, tmp_path) as tasks:
        tasks.add("pickle")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(RecoveryError, match="checkpoint"):
        coopy.open(Tasks, tmp_path, serializer=json_serializer())
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("damage", ["unknown_type", "version", "truncated", "bad_node"])
def test_json_decode_failures_obey_recovery_policy(tmp_path, damage):
    codec = json_serializer()
    with coopy.open(Tasks, tmp_path, serializer=codec) as tasks:
        tasks.add("ok")
        tasks.add("damaged")
    journal = next(tmp_path.glob("transaction*"))
    lines = journal.read_bytes().splitlines(keepends=True)
    document = json.loads(lines[1])
    if damage == "unknown_type":
        document["value"]["n"] = "untrusted.module.Class"
    elif damage == "version":
        document["version"] = 2
    elif damage == "bad_node":
        document["value"]["t"] = "invalid"
    lines[1] = (json.dumps(document) + "\n").encode()
    if damage == "truncated":
        lines[1] = lines[1][:-1]
    journal.write_bytes(b"".join(lines))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(RecoveryError) as caught:
        coopy.open(Tasks, tmp_path, serializer=codec)
    assert caught.value.report.stop.kind == "decode"
    result = coopy.open(Tasks, tmp_path, serializer=codec, recovery="salvage")
    assert result.system.items == [("ok", 0)]
    assert result.report.replayed == 1
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def legacy_action(path, serializer=None, version=None):
    with coopy.open(Tasks, path, serializer=serializer):
        pass
    action = Action(1, "add", datetime(2020, 1, 1), ("legacy",), {})
    action.raised = False
    if version is None:
        del action.schema_version
    else:
        action.schema_version = version
    journal = next(path.glob("transaction*"))
    journal.write_bytes((serializer or coopy.PickleSerializer()).dumps(action))


@pytest.mark.parametrize("codec", [None, coopy.PickleSerializer(), json_serializer()])
def test_legacy_action_upgrades_signature_and_writes_new_version(tmp_path, monkeypatch, codec):
    legacy_action(tmp_path, codec)

    def add(self, text, priority):
        self.items.append((text, priority))

    monkeypatch.setattr(Tasks, "add", add)
    schemas = coopy.ActionSchemas({"add": 3})
    schemas.register("add", 1, lambda args, kwargs: (args, dict(kwargs, priority=0)))
    schemas.register(
        "add", 2, lambda args, kwargs: (args, dict(kwargs, priority=kwargs["priority"] + 1))
    )
    with coopy.open(Tasks, tmp_path, serializer=codec, schemas=schemas) as tasks:
        assert tasks.items == [("legacy", 1)]
        tasks.add("new", 5)
        journal = tasks.publisher.subscribers[0].file.name
    with open(journal, "rb") as file:
        action = (codec or coopy.PickleSerializer()).reader(file).load()
        assert action.schema_version == 3
    with coopy.open(Tasks, tmp_path, serializer=codec, schemas=schemas) as tasks:
        assert tasks.items == [("legacy", 1), ("new", 5)]


@pytest.mark.parametrize(
    "failure", ["future", "missing", "throws", "shape", "signature", "invalid_version"]
)
def test_invalid_upgrades_fail_before_domain_execution(tmp_path, failure):
    legacy_action(
        tmp_path,
        version=4 if failure == "future" else (True if failure == "invalid_version" else None),
    )
    schemas = coopy.ActionSchemas({"add": 2})
    if failure not in ("missing", "future", "invalid_version"):

        def upgrade(args, kwargs):
            if failure == "throws":
                raise RuntimeError("bad upgrade")
            if failure == "shape":
                return None
            return args, {"unexpected": True}

        schemas.register("add", 1, upgrade)
    with pytest.raises(RecoveryError) as caught:
        coopy.open(Tasks, tmp_path, schemas=schemas)
    assert caught.value.report.stop.kind == "decode"
    result = coopy.open(Tasks, tmp_path, schemas=schemas, recovery="salvage")
    assert result.system.items == []
    assert not result.report.stop.state_may_be_changed


def test_renamed_class_snapshot_and_journal_fixture(tmp_path):
    # Materialize a genuine pickle GLOBAL reference whose module disappears.
    module = types.ModuleType("old_tasks_module")
    old = type("OldTasks", (Tasks,), {"__module__": module.__name__})
    module.OldTasks = old
    sys.modules[module.__name__] = module
    try:
        with coopy.open(old, tmp_path) as tasks:
            tasks.add("old")
    finally:
        del sys.modules[module.__name__]
    with pytest.raises(RecoveryError):
        coopy.open(Tasks, tmp_path)
    codec = coopy.PickleSerializer(class_aliases={("old_tasks_module", "OldTasks"): Tasks})
    with coopy.open(Tasks, tmp_path, serializer=codec) as tasks:
        assert tasks.items == [("old", 0)]
        coopy.control(tasks).take_snapshot()
    with coopy.open(Tasks, tmp_path) as tasks:
        assert tasks.items == [("old", 0)]


def test_integrity_verifies_before_custom_decoder(tmp_path):
    codec = json_serializer()
    with coopy.open(Tasks, tmp_path, serializer=codec, secret=b"key") as tasks:
        tasks.add("signed")
    journal = next(tmp_path.glob("transaction*"))
    journal.write_bytes(journal.read_bytes()[:-1])

    class ForbiddenCodec:
        def __getattr__(self, name):
            raise AssertionError("Codec accessed before verification")

    with pytest.raises(RecoveryError, match="verification"):
        coopy.open(Tasks, tmp_path, serializer=ForbiddenCodec(), secret=b"key")


def test_registry_decoder_contract_and_names():
    registry = coopy.TypeRegistry()
    registry.register("tasks", Tasks, encode=lambda obj: {}, decode=lambda state: None)
    codec = coopy.JsonSerializer(registry)
    with pytest.raises(coopy.SerializationError, match="wrong type"):
        codec.loads(codec.dumps(Tasks()))
    with pytest.raises(coopy.SerializationError):
        registry.register("tasks", Tasks, encode=vars, decode=restore_tasks)
    with pytest.raises(coopy.SerializationError):
        registry.register("coopy.custom", Tasks, encode=vars, decode=restore_tasks)


def test_unknown_journal_value_poisoning(tmp_path):
    with coopy.open(Tasks, tmp_path, serializer=json_serializer()) as tasks:
        with pytest.raises(PersistenceError) as caught:
            tasks.add(object())
        assert isinstance(caught.value.__cause__, coopy.SerializationError)
        with pytest.raises(PersistenceError, match="disabled"):
            tasks.add("refused")


def test_alias_applies_to_journal_arguments(tmp_path):
    module = types.ModuleType("old_value_module")
    old = type("OldValue", (), {"__module__": module.__name__})
    module.OldValue = old
    sys.modules[module.__name__] = module
    try:
        value = old()
        value.text = "renamed"
        with coopy.open(Tasks, tmp_path) as tasks:
            tasks.add(value)
    finally:
        del sys.modules[module.__name__]
    codec = coopy.PickleSerializer(class_aliases={("old_value_module", "OldValue"): RenamedValue})
    with coopy.open(Tasks, tmp_path, serializer=codec) as tasks:
        value = tasks.items[0][0]
        assert isinstance(value, RenamedValue)
        assert value.text == "renamed"


class RenamedValue:
    pass


def test_json_new_process_restart(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    with coopy.open(Tasks, tmp_path, serializer=json_serializer()) as tasks:
        tasks.add("before")
    source = """
import coopy
from tests.functional.test_serialization import Tasks, json_serializer
with coopy.open(Tasks, '.', serializer=json_serializer()) as tasks:
    assert tasks.items == [('before', 0)]
    coopy.control(tasks).take_snapshot()
    tasks.add('after')
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    subprocess.run([sys.executable, "-c", source], cwd=tmp_path, env=env, check=True, timeout=20)
    with coopy.open(Tasks, tmp_path, serializer=json_serializer()) as tasks:
        assert tasks.items == [("before", 0), ("after", 0)]


def test_custom_serializer_protocol(tmp_path):
    class Codec:
        def __init__(self):
            self.delegate = coopy.PickleSerializer()
            self.calls = []

        def reader(self, file):
            self.calls.append("reader")
            return self.delegate.reader(file)

        def writer(self, file):
            self.calls.append("writer")
            return self.delegate.writer(file)

        def loads(self, payload):
            self.calls.append("loads")
            return self.delegate.loads(payload)

        def dumps(self, value):
            self.calls.append("dumps")
            return self.delegate.dumps(value)

    codec = Codec()
    for secret in (None, b"signed"):
        path = tmp_path / ("signed" if secret else "unsigned")
        with coopy.open(Tasks, path, serializer=codec, secret=secret) as tasks:
            tasks.add("custom")
        with coopy.open(Tasks, path, serializer=codec, secret=secret) as tasks:
            assert tasks.items == [("custom", 0)]
    assert set(codec.calls) == {"reader", "writer", "loads", "dumps"}


def test_json_checkpoint_unknown_type_and_version(tmp_path):
    codec = json_serializer()
    with coopy.open(Tasks, tmp_path, serializer=codec):
        pass
    snapshot = next(tmp_path.glob("snapshot*"))
    original = json.loads(snapshot.read_bytes())
    for change in ("type", "version"):
        document = json.loads(json.dumps(original))
        if change == "type":
            document["value"]["n"] = "not.registered"
        else:
            document["version"] = 99
        snapshot.write_text(json.dumps(document) + "\n")
        with pytest.raises(RecoveryError, match="checkpoint"):
            coopy.open(Tasks, tmp_path, serializer=codec)
        result = coopy.open(Tasks, tmp_path, serializer=codec, recovery="salvage")
        assert result.system is None
        assert result.report.stop.kind == "checkpoint"


def test_json_nonfinite_exponent_rejected():
    with pytest.raises(coopy.SerializationError):
        coopy.JsonSerializer().loads(b'{"format":"coopy-json","version":1,"value":1e999}')


@pytest.mark.parametrize(
    "node",
    [
        [],
        {"t": "list", "v": None},
        {"t": "unknown", "v": []},
        float("nan"),
        {"t": "bytes", "v": "!"},
    ],
    ids=["untagged", "invalid-collection", "unknown-tag", "nonfinite", "invalid-base64"],
)
def test_malformed_json_checkpoint_stops_without_writing(tmp_path, node):
    codec = json_serializer()
    with coopy.open(Tasks, tmp_path, serializer=codec):
        pass
    snapshot = next(tmp_path.glob("snapshot*"))
    snapshot.write_text(json.dumps({"format": "coopy-json", "version": 1, "value": node}) + "\n")
    original = {path: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(RecoveryError, match="checkpoint") as caught:
        coopy.open(Tasks, tmp_path, serializer=codec)
    assert isinstance(caught.value.__cause__, coopy.SerializationError)
    result = coopy.open(Tasks, tmp_path, serializer=codec, recovery="salvage")
    assert result.system is None
    assert result.report.stop.kind == "checkpoint"
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == original


@pytest.mark.parametrize("version", [0, -1, True, 1.5, "2"])
def test_invalid_action_schema_version_rejected(version):
    with pytest.raises(coopy.SerializationError, match="positive integers"):
        coopy.ActionSchemas({"add": version})


@pytest.mark.parametrize("version", [0, 2, True])
def test_invalid_upgrade_registration_rejected(version):
    schemas = coopy.ActionSchemas({"add": 2})
    with pytest.raises(coopy.SerializationError, match="unique and advance"):
        schemas.register("add", version, lambda args, kwargs: (args, kwargs))


def test_codec_rotation_native_path(tmp_path):
    # A backslash is a legal filename character on POSIX, not a separator.
    with coopy.open(Tasks, tmp_path / "native\\path", serializer=json_serializer()) as tasks:
        tasks.publisher.subscribers[0].file.max_size = 1
        tasks.add("rotated")
        coopy.control(tasks).take_snapshot()
        tasks.add("after")
    with coopy.open(Tasks, tmp_path / "native\\path", serializer=json_serializer()) as tasks:
        assert tasks.items == [("rotated", 0), ("after", 0)]
