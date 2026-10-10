"""Data directory manifest: the on-disk format version and storage settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from coopy import fileutils
from coopy.error import FormatError

MANIFEST_FILE = "coopy.json"

# Format 0 is every directory written before manifests existed.
FORMAT_VERSION = 1


CUSTOM_PREFIX = "custom:"


def serializer_name(serializer: Any) -> str:
    """A codec's declared ``format_name``, or ``custom:<class path>`` if undeclared."""
    if serializer is None:
        return "pickle"
    # A class attribute: reading it must not touch the codec instance.
    name = getattr(type(serializer), "format_name", None)
    if isinstance(name, str) and name and not name.startswith(CUSTOM_PREFIX):
        return name
    return f"{CUSTOM_PREFIX}{type(serializer).__module__}.{type(serializer).__qualname__}"


def read(basedir: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Return the manifest, or None for a legacy (format 0) directory."""
    path = Path(basedir) / MANIFEST_FILE
    try:
        data = json.loads(path.read_bytes())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise FormatError(f"Unreadable manifest {str(path)!r}: {error}") from error
    version = data.get("format_version") if isinstance(data, dict) else None
    if type(version) is not int or version < 0:
        raise FormatError(f"Manifest {str(path)!r} has no valid format_version")
    if version > FORMAT_VERSION:
        raise FormatError(
            f"Data directory {str(Path(basedir))!r} uses on-disk format {version}, "
            f"newer than format {FORMAT_VERSION} supported by this coopy; upgrade coopy"
        )
    return data


def check(
    basedir: str | os.PathLike[str], *, serializer: Any, secret: bytes | None
) -> dict[str, Any] | None:
    """Fail before decoding when the directory is newer or opened differently."""
    manifest = read(basedir)
    if manifest is None:
        return None
    expected = manifest.get("serializer")
    actual = serializer_name(serializer)
    # Undeclared custom codecs may wrap another format, so only named ones compare.
    declared = not (str(expected).startswith(CUSTOM_PREFIX) or actual.startswith(CUSTOM_PREFIX))
    if declared and expected != actual:
        raise FormatError(
            f"Data directory {str(Path(basedir))!r} was written with serializer "
            f"{expected!r} but is being opened with {actual!r}; pass the original "
            "serializer (converting formats needs an explicit export/import)"
        )
    signed = manifest.get("signed")
    if signed is True and secret is None:
        raise FormatError(
            f"Data directory {str(Path(basedir))!r} is HMAC-signed; pass its secret to open it"
        )
    if signed is False and secret is not None:
        raise FormatError(
            f"Data directory {str(Path(basedir))!r} is unsigned; it cannot be opened with a secret"
        )
    return manifest


def write(
    basedir: str | os.PathLike[str],
    *,
    serializer: Any,
    secret: bytes | None,
    durability: str = "buffered",
) -> None:
    """Atomically write the manifest; callers hold the directory lock."""
    from coopy import __version__

    manifest = {
        "format_version": FORMAT_VERSION,
        "serializer": serializer_name(serializer),
        "signed": secret is not None,
        "coopy_version": __version__,
    }
    path = Path(basedir) / MANIFEST_FILE
    temporary = path.with_name(MANIFEST_FILE + ".tmp")
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    if durability == "sync":
        fileutils.sync_directory(basedir)
