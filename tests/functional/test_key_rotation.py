"""Rotate integrity secrets: read with accepted keys, sign with the newest."""

import io
from pathlib import Path

import pytest

import coopy
from coopy.base import init_persistent_system
from coopy.error import ConfigurationError
from coopy.integrity import IDENTITY_FILE, Integrity, IntegrityError
from coopy.restore import RecoveryError

from .test_integrity import rejects_without_unpickling
from .test_recovery_policy import Ledger

A = b"test-only-key-a"
B = b"test-only-key-b"
C = b"test-only-key-c"


def signed_with_a(directory):
    with coopy.open(Ledger, directory, secret=A) as ledger:
        ledger.add("a1")
        coopy.control(ledger).take_snapshot()
        ledger.add("a2")


def identity(directory):
    return Integrity.open(directory, [A, B]).system_id


def verifies_with(directory, filename, key):
    """Whether every envelope in ``filename`` verifies with exactly ``key``."""
    integrity = Integrity(key, identity(directory))
    data = (directory / filename).read_bytes()
    stream = io.BytesIO(data)
    try:
        while stream.tell() < len(data):
            integrity.read(stream, filename)
    except IntegrityError:
        return False
    return True


def newest(directory, prefix):
    return sorted(p.name for p in directory.iterdir() if p.name.startswith(prefix))[-1]


def test_rotated_list_opens_old_storage_and_signs_new_records_with_newest(tmp_path):
    signed_with_a(tmp_path)
    with coopy.open(Ledger, tmp_path, secret=[B, A]) as ledger:
        assert ledger.values == ["a1", "a2"]
        ledger.add("b1")
        journal = Path(ledger.publisher.subscribers[0].file.name).name
    assert verifies_with(tmp_path, journal, B)
    assert not verifies_with(tmp_path, journal, A)

    with coopy.open(Ledger, tmp_path, secret=(B, A)) as ledger:
        coopy.control(ledger).take_snapshot()
        ledger.add("b2")
    snapshot = newest(tmp_path, "snapshot_")
    assert verifies_with(tmp_path, snapshot, B)
    assert not verifies_with(tmp_path, snapshot, A)
    with coopy.open(Ledger, tmp_path, secret=[B, A]) as ledger:
        assert ledger.values == ["a1", "a2", "b1", "b2"]


def test_mixed_directory_still_needs_old_key(tmp_path, monkeypatch):
    signed_with_a(tmp_path)
    with coopy.open(Ledger, tmp_path, secret=[B, A]) as ledger:
        ledger.add("b1")
    # The identity and older records are still signed with A only.
    report = rejects_without_unpickling(tmp_path, monkeypatch, secret=B)
    assert report.stop.position.file.endswith(IDENTITY_FILE)
    # Dropping the new key fails at the first record signed with it.
    report = rejects_without_unpickling(tmp_path, monkeypatch, secret=[A])
    assert report.stop.position.record >= 1


@pytest.mark.parametrize("secret", [C, [C], [C, B]])
def test_wrong_keys_fail_before_decoding(tmp_path, monkeypatch, secret):
    signed_with_a(tmp_path)
    rejects_without_unpickling(tmp_path, monkeypatch, secret=secret)


def test_resign_through_convert_retires_old_key(tmp_path, monkeypatch):
    src, dst = tmp_path / "src", tmp_path / "dst"
    signed_with_a(src)
    with coopy.open(Ledger, src, secret=[B, A]) as ledger:
        ledger.add("b1")

    coopy.convert(src, dst, secret=[B, A], new_secret=B)

    (snapshot,) = dst.glob("snapshot_*.dat")
    assert verifies_with(dst, snapshot.name, B)
    assert not verifies_with(dst, snapshot.name, A)
    with pytest.raises(IntegrityError, match="identity"):
        Integrity.open(dst, A)
    with coopy.open(Ledger, dst, secret=B) as ledger:
        assert ledger.values == ["a1", "a2", "b1"]
        ledger.add("b2")
    with coopy.open(Ledger, dst, secret=[B, A]) as ledger:
        assert ledger.values == ["a1", "a2", "b1", "b2"]
    # A is retired: alone it fails before anything is decoded.
    rejects_without_unpickling(dst, monkeypatch, secret=A)


def test_new_signed_directory_uses_first_key(tmp_path):
    with coopy.open(Ledger, tmp_path, secret=[B, A]) as ledger:
        ledger.add("x")
    with coopy.open(Ledger, tmp_path, secret=B) as ledger:
        assert ledger.values == ["x"]
    with pytest.raises(RecoveryError, match="verification"):
        coopy.open(Ledger, tmp_path, secret=A)


@pytest.mark.parametrize("secret", [[], (), [A, b""], [A, "text"], "text", {A}, [[A]]])
def test_invalid_key_lists_are_rejected(tmp_path, secret):
    with pytest.raises(ConfigurationError, match="secret must be"):
        init_persistent_system(Ledger, tmp_path, secret=secret)
    with pytest.raises(ConfigurationError, match="secret must be"):
        coopy.convert(tmp_path, tmp_path / "dst", new_secret=secret)
