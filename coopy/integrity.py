"""Versioned HMAC envelopes. No pickle operation belongs in this module."""

import hashlib
import hmac
import os
import struct
from os import PathLike
from typing import BinaryIO, Sequence

from coopy import fileutils
from coopy.error import ConfigurationError
from coopy.error import IntegrityError as IntegrityError

MAGIC = b"COOPY-HMAC-1\x00"
IDENTITY_FILE = ".coopy-integrity"
HEADER = struct.Struct("!Q")
TAG_SIZE = hashlib.sha256().digest_size


# One key, or accepted keys newest first: records verify with any, new ones use the first.
Secret = bytes | Sequence[bytes]


def secret_keys(secret: Secret | None) -> tuple[bytes, ...] | None:
    """Normalize ``secret`` to its accepted keys, newest (the signing key) first."""
    if secret is None:
        return None
    keys = (secret,) if isinstance(secret, bytes) else secret
    if (
        not isinstance(keys, (list, tuple))
        or not keys
        or any(not isinstance(key, bytes) or not key for key in keys)
    ):
        raise ConfigurationError(
            "secret must be nonempty bytes, a nonempty list of nonempty bytes, or None"
        )
    return tuple(keys)


def validate_secret(secret: Secret | None) -> None:
    secret_keys(secret)


class Integrity:
    def __init__(self, secret: Secret, system_id: bytes) -> None:
        keys = secret_keys(secret)
        assert keys is not None
        self.keys = keys
        self.secret = keys[0]
        self.system_id = system_id

    @classmethod
    def open(
        cls,
        basedir: str | PathLike[str],
        secret: Secret,
        *,
        create: bool = False,
        durability: str = "buffered",
    ) -> "Integrity":
        keys = secret_keys(secret)
        assert keys is not None
        filename = os.path.join(basedir, IDENTITY_FILE)
        if create:
            identity = MAGIC + os.urandom(32)
            tag = hmac.digest(keys[0], b"identity\x00" + identity, "sha256")
            # Exclusive creation prevents silently replacing an existing identity.
            with open(filename, "xb") as file:
                file.write(identity + tag)
                file.flush()
                os.fsync(file.fileno())
            if durability == "sync":
                fileutils.sync_directory(basedir)
        try:
            with open(filename, "rb") as file:
                data = file.read(len(MAGIC) + 32 + TAG_SIZE + 1)
        except FileNotFoundError as error:
            raise IntegrityError(
                "Missing integrity identity; unsigned storage cannot be opened with a secret"
            ) from error
        size = len(MAGIC) + 32
        if (
            len(data) != size + TAG_SIZE
            or not data.startswith(MAGIC)
            or not any(
                hmac.compare_digest(
                    data[size:], hmac.digest(key, b"identity\x00" + data[:size], "sha256")
                )
                for key in keys
            )
        ):
            raise IntegrityError(
                "Integrity identity verification failed (wrong secret or tampered identity)"
            )
        return cls(keys, data[len(MAGIC) : size])

    def _mac(
        self,
        key: bytes,
        filename: str | PathLike[str],
        offset: int,
        header: bytes,
        payload: bytes,
    ) -> bytes:
        # Bind to system, file kind/number, and record location, so valid
        # envelopes cannot be transplanted between systems/files/positions.
        context = (
            MAGIC
            + self.system_id
            + os.path.basename(filename).encode("utf-8")
            + b"\x00"
            + HEADER.pack(offset)
            + header
        )
        mac = hmac.new(key, context, hashlib.sha256)
        mac.update(payload)
        return mac.digest()

    def encode(self, payload: bytes, filename: str | PathLike[str], offset: int = 0) -> bytes:
        header = MAGIC + HEADER.pack(len(payload))
        return header + payload + self._mac(self.secret, filename, offset, header, payload)

    def read(self, file: BinaryIO, filename: str | PathLike[str]) -> bytes:
        offset = file.tell()
        header = file.read(len(MAGIC) + HEADER.size)
        if len(header) != len(MAGIC) + HEADER.size or not header.startswith(MAGIC):
            raise IntegrityError("Missing or truncated signed record header")
        (size,) = HEADER.unpack(header[len(MAGIC) :])
        # Check available bytes before allocating using an untrusted length.
        start = file.tell()
        file.seek(0, os.SEEK_END)
        remaining = file.tell() - start
        file.seek(start)
        if size > remaining - TAG_SIZE:
            raise IntegrityError("Truncated signed record or missing HMAC tag")
        payload = file.read(size)
        tag = file.read(TAG_SIZE)
        if not any(
            hmac.compare_digest(tag, self._mac(key, filename, offset, header, payload))
            for key in self.keys
        ):
            raise IntegrityError("HMAC verification failed (wrong secret or tampered record)")
        return payload
