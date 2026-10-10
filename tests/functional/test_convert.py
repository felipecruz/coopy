"""Convert a data directory to another serializer or signing setting."""

import json

import pytest

import coopy
from coopy.error import ConfigurationError, FormatError
from coopy.integrity import IDENTITY_FILE
from coopy.manifest import MANIFEST_FILE
from coopy.restore import RecoveryError

from .test_serialization import Tasks, json_serializer

SECRET = b"test-only-convert-secret"
OTHER = b"test-only-other-secret"


def populate(directory, **options):
    with coopy.open(Tasks, directory, **options) as tasks:
        tasks.add("checkpoint", 1)
        coopy.control(tasks).take_snapshot()
        tasks.add("journal", 2)
        tasks.timed("clock")
        with pytest.raises(ValueError, match="expected"):
            tasks.fail("failure")
        return tasks.items[:]


def storage(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir() if p.name != "coopy.lock"}


@pytest.mark.parametrize(
    "source, target",
    [
        ({}, {"new_serializer": "json"}),
        ({"serializer": "json"}, {"new_serializer": None}),
        ({"serializer": "json"}, {"new_serializer": coopy.PickleSerializer()}),
        ({}, {"new_secret": SECRET}),
        ({"secret": SECRET}, {"new_secret": None}),
        ({"serializer": "json", "secret": SECRET}, {"new_secret": OTHER}),
        ({"secret": SECRET}, {}),
    ],
)
def test_round_trip_restores_identical_state(tmp_path, source, target):
    def resolve(options):
        return {
            key: json_serializer() if value == "json" else value for key, value in options.items()
        }

    source, target = resolve(source), resolve(target)
    src, dst = tmp_path / "src", tmp_path / "nested" / "dst"
    expected = populate(src, **source)
    before = storage(src)

    report = coopy.convert(src, dst, **source, **target)

    assert report.complete and report.replayed == 3 and report.expected_failures == 1
    assert storage(src) == before
    reopen = {
        "serializer": target.get("new_serializer", source.get("serializer")),
        "secret": target.get("new_secret", source.get("secret")),
    }
    written = json.loads((dst / MANIFEST_FILE).read_text())
    assert written["signed"] is (reopen["secret"] is not None)
    assert (dst / IDENTITY_FILE).exists() is (reopen["secret"] is not None)
    with coopy.open(Tasks, dst, **reopen) as converted:
        assert converted.items == expected
        report = coopy.control(converted).recovery_report
        assert report.replayed == 0
        converted.add("after", 3)
    with coopy.open(Tasks, dst, **reopen) as converted:
        assert converted.items == expected + [("after", 3)]
    with coopy.open(Tasks, src, **source) as original:
        assert original.items == expected


def test_converted_directory_rejects_old_settings(tmp_path):
    populate(tmp_path / "src")
    coopy.convert(tmp_path / "src", tmp_path / "dst", new_secret=SECRET)
    with pytest.raises(FormatError, match="HMAC-signed"):
        coopy.open(Tasks, tmp_path / "dst")
    with pytest.raises(RecoveryError, match="verification"):
        coopy.open(Tasks, tmp_path / "dst", secret=OTHER)


def test_existing_empty_destination_is_used(tmp_path):
    expected = populate(tmp_path / "src")
    (tmp_path / "dst").mkdir()
    coopy.convert(tmp_path / "src", tmp_path / "dst", new_serializer=json_serializer())
    with coopy.open(Tasks, tmp_path / "dst", serializer=json_serializer()) as converted:
        assert converted.items == expected


@pytest.mark.parametrize("kind", ["file", "dir", "regular"])
def test_non_empty_destination_is_refused_untouched(tmp_path, kind):
    populate(tmp_path / "src")
    dst = tmp_path / "dst"
    if kind == "regular":
        dst.write_bytes(b"keep")
    else:
        dst.mkdir()
        (dst / "keep").mkdir() if kind == "dir" else (dst / "keep").write_bytes(b"keep")
    snapshot = sorted(p.name for p in tmp_path.rglob("*"))
    with pytest.raises(ConfigurationError, match="not empty|not a directory"):
        coopy.convert(tmp_path / "src", dst, new_secret=SECRET)
    assert sorted(p.name for p in tmp_path.rglob("*")) == snapshot


def test_same_directory_and_missing_source_are_refused(tmp_path):
    with pytest.raises(ConfigurationError, match="not a data directory"):
        coopy.convert(tmp_path / "missing", tmp_path / "dst")
    (tmp_path / "empty").mkdir()
    with pytest.raises(ConfigurationError, match="different"):
        coopy.convert(tmp_path / "empty", tmp_path / "empty")
    assert not (tmp_path / "dst").exists()


@pytest.mark.parametrize("existing", [False, True])
def test_failed_recovery_leaves_nothing_behind(tmp_path, existing):
    src = tmp_path / "src"
    populate(src, secret=SECRET)
    before = storage(src)
    dst = tmp_path / "out" / "dst"
    if existing:
        dst.mkdir(parents=True)
    with pytest.raises(RecoveryError, match="verification"):
        coopy.convert(src, dst, secret=OTHER)
    assert storage(src) == before
    if existing:
        assert list(dst.iterdir()) == []
    else:
        assert not (tmp_path / "out").exists()


def test_source_settings_are_checked(tmp_path):
    populate(tmp_path / "src", serializer=json_serializer())
    with pytest.raises(FormatError, match="serializer"):
        coopy.convert(tmp_path / "src", tmp_path / "dst")
    assert not (tmp_path / "dst").exists()


def test_failed_write_removes_partial_destination(tmp_path):
    populate(tmp_path / "src")
    with pytest.raises(coopy.SerializationError, match="Unregistered"):
        coopy.convert(tmp_path / "src", tmp_path / "dst", new_serializer=coopy.JsonSerializer())
    assert not (tmp_path / "dst").exists()


def test_open_source_is_refused(tmp_path):
    with coopy.open(Tasks, tmp_path / "src") as tasks:
        tasks.add("open", 1)
        with pytest.raises(coopy.error.LockError):
            coopy.convert(tmp_path / "src", tmp_path / "dst")
    assert not (tmp_path / "dst").exists()


def test_compressed_target(tmp_path):
    pytest.importorskip("zstandard")
    expected = populate(tmp_path / "src")
    coopy.convert(tmp_path / "src", tmp_path / "dst", snapshot_compression="zstd")
    (snapshot,) = [p for p in (tmp_path / "dst").iterdir() if p.name.startswith("snapshot_")]
    assert snapshot.read_bytes().startswith(b"COOPY-COMPRESSED-1")
    with coopy.open(Tasks, tmp_path / "dst") as converted:
        assert converted.items == expected
