"""Snapshot-only compression envelopes, inside HMAC when authentication is used."""

import importlib

from coopy.error import ConfigurationError

MAGIC = b"COOPY-COMPRESSED-1\x00"


def validate_compression(codec):
    if codec not in (None, "zstd", "lz4"):
        raise ConfigurationError("snapshot_compression must be None, 'zstd', or 'lz4'")
    if codec is not None:
        try:
            return importlib.import_module("zstandard" if codec == "zstd" else "lz4.frame")
        except ImportError as error:
            raise ConfigurationError(f"Install coopy[{codec}] to use {codec} snapshots") from error


def compress(payload, codec):
    module = validate_compression(codec)
    if codec is None:
        return payload
    if codec == "zstd":
        data = module.ZstdCompressor(write_checksum=True).compress(payload)
    else:
        data = module.compress(payload, content_checksum=True)
    return MAGIC + codec.encode("ascii") + b"\x00" + data


def decompress(payload):
    if not payload.startswith(MAGIC):
        return payload
    codec, separator, data = payload[len(MAGIC) :].partition(b"\x00")
    if not separator or codec not in (b"zstd", b"lz4"):
        raise ValueError("Unsupported compressed snapshot format")
    module = validate_compression(codec.decode("ascii"))
    if codec == b"zstd":
        return module.ZstdDecompressor().decompress(data, allow_extra_data=False)
    result, consumed = module.decompress(data, return_bytes_read=True)
    if consumed != len(data):
        raise ValueError("Trailing bytes after compressed snapshot")
    return result
