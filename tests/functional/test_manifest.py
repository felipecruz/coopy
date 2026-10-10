"""F23: the data directory manifest versions the on-disk format."""

import json
import shutil
from pathlib import Path

import pytest

import coopy
from coopy import locking, manifest, restore, snapshot
from coopy.error import FormatError
from coopy.manifest import FORMAT_VERSION, MANIFEST_FILE
from tests.legacy_domain import Notebook

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "legacy"
SECRET = b"manifest-secret"

# Each fixture was written by that release (0.3.1 and 0.4b under Python 3.9,
# 0.5.0 from the F22 commit); the expected notes are what that release restored.
LEGACY = {
    "v0_3": ["before checkpoint"],
    "v0_4": ["before checkpoint"],
    "v0_5": ["before checkpoint", "after reopen"],
}


def json_serializer():
    registry = coopy.TypeRegistry()
    registry.register(
        "notebook",
        Notebook,
        encode=lambda obj: vars(obj),
        decode=lambda state: _notebook(state),
    )
    return coopy.JsonSerializer(registry)


def _notebook(state):
    result = Notebook()
    result.__dict__.update(state)
    return result


def written(path):
    with coopy.open(Notebook, path) as notebook:
        notebook.add("one")
    return json.loads((path / MANIFEST_FILE).read_text())


def contents(path):
    return {p.name: p.read_bytes() for p in path.iterdir() if p.name != locking.LOCK_FILE}


def forbid_decoding(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("nothing may be decoded")

    monkeypatch.setattr(restore, "Unpickler", forbidden)
    monkeypatch.setattr(snapshot, "Unpickler", forbidden)


def test_new_directory_gets_manifest(tmp_path):
    data = written(tmp_path / "data")
    assert data == {
        "coopy_version": coopy.__version__,
        "format_version": FORMAT_VERSION,
        "serializer": "pickle",
        "signed": False,
    }


@pytest.mark.parametrize(
    "options, serializer, signed",
    [
        ({"serializer": "json"}, "json", False),
        ({"secret": SECRET}, "pickle", True),
        ({"serializer": "json", "secret": SECRET}, "json", True),
    ],
)
def test_manifest_records_serializer_and_signing(tmp_path, options, serializer, signed):
    if options.get("serializer") == "json":
        options = {**options, "serializer": json_serializer()}
    with coopy.open(Notebook, tmp_path, **options) as notebook:
        notebook.add("one")
    data = json.loads((tmp_path / MANIFEST_FILE).read_text())
    assert (data["serializer"], data["signed"]) == (serializer, signed)
    with coopy.open(Notebook, tmp_path, **options) as notebook:
        assert notebook.notes == ["one"]


@pytest.mark.parametrize("version", sorted(LEGACY))
def test_legacy_fixture_restores_and_gains_manifest(tmp_path, version):
    data = tmp_path / version
    shutil.copytree(FIXTURES / version, data)
    result = coopy.open(Notebook, data, recovery="salvage")
    assert result.system.notes == LEGACY[version]
    assert not (data / MANIFEST_FILE).exists(), "salvage must not write"

    with coopy.open(Notebook, data) as notebook:
        assert notebook.notes == LEGACY[version]
        notebook.add("upgraded")
    stored = json.loads((data / MANIFEST_FILE).read_text())
    assert stored["format_version"] == FORMAT_VERSION
    assert (stored["serializer"], stored["signed"]) == ("pickle", False)
    with coopy.open(Notebook, data) as notebook:
        assert notebook.notes == LEGACY[version] + ["upgraded"]


def test_legacy_fixture_with_wrong_settings_gets_no_manifest(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(FIXTURES / "v0_5", data)
    with pytest.raises(restore.RecoveryError):
        coopy.open(Notebook, data, secret=SECRET)
    assert not (data / MANIFEST_FILE).exists()
    with coopy.open(Notebook, data) as notebook:
        assert notebook.notes == LEGACY["v0_5"]


@pytest.mark.parametrize("mode", ["strict", "salvage", "restore"])
def test_future_format_fails_before_decoding(tmp_path, monkeypatch, mode):
    data = tmp_path / "data"
    stored = written(data)
    stored["format_version"] = FORMAT_VERSION + 1
    (data / MANIFEST_FILE).write_text(json.dumps(stored))
    before = contents(data)
    forbid_decoding(monkeypatch)
    with pytest.raises(FormatError, match=f"format {FORMAT_VERSION + 1}.*upgrade coopy"):
        if mode == "restore":
            restore.restore(Notebook(), data)
        else:
            coopy.open(Notebook, data, recovery=mode)
    assert contents(data) == before


@pytest.mark.parametrize("text", ["{", "[]", '{"format_version": "1"}', "{}"])
def test_unreadable_manifest_fails_clearly(tmp_path, monkeypatch, text):
    data = tmp_path / "data"
    written(data)
    (data / MANIFEST_FILE).write_text(text)
    forbid_decoding(monkeypatch)
    with pytest.raises(FormatError, match="anifest"):
        coopy.open(Notebook, data)


@pytest.mark.parametrize(
    "create, reopen, message",
    [
        ({}, {"serializer": "json"}, "serializer 'pickle' but is being opened with 'json'"),
        ({"serializer": "json"}, {}, "serializer 'json' but is being opened with 'pickle'"),
        ({}, {"secret": SECRET}, "is unsigned"),
        ({"secret": SECRET}, {}, "HMAC-signed; pass its secret"),
    ],
)
def test_switching_settings_fails_with_clear_message(
    tmp_path, monkeypatch, create, reopen, message
):
    def resolve(options):
        if options.get("serializer") == "json":
            return {**options, "serializer": json_serializer()}
        return options

    with coopy.open(Notebook, tmp_path, **resolve(create)) as notebook:
        notebook.add("one")
    before = contents(tmp_path)
    forbid_decoding(monkeypatch)
    for recovery in ("strict", "salvage"):
        with pytest.raises(FormatError, match=message):
            coopy.open(Notebook, tmp_path, recovery=recovery, **resolve(reopen))
    assert contents(tmp_path) == before


def test_undeclared_custom_serializer_is_not_compared(tmp_path):
    class Wrapped(coopy.PickleSerializer):
        format_name = None

    with coopy.open(Notebook, tmp_path) as notebook:
        notebook.add("one")
    with coopy.open(Notebook, tmp_path, serializer=Wrapped()) as notebook:
        assert notebook.notes == ["one"]
    assert manifest.read(tmp_path)["serializer"] == "pickle"


def test_manifest_is_written_under_the_directory_lock(tmp_path, monkeypatch):
    real_write = manifest.write
    seen = []

    def observe(basedir, **options):
        seen.append(bool(locking._held))
        real_write(basedir, **options)

    monkeypatch.setattr(manifest, "write", observe)
    shutil.copytree(FIXTURES / "v0_5", tmp_path / "legacy")
    for path in (tmp_path / "new", tmp_path / "legacy"):
        coopy.control(coopy.open(Notebook, path)).close()
    assert seen == [True, True]
