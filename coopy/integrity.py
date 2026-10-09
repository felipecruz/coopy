"""Versioned HMAC envelopes. No pickle operation belongs in this module."""
import hashlib
import hmac
import os
import struct

from coopy import fileutils


MAGIC = b'COOPY-HMAC-1\x00'
IDENTITY_FILE = '.coopy-integrity'
HEADER = struct.Struct('!Q')
TAG_SIZE = hashlib.sha256().digest_size


class IntegrityError(ValueError):
    """Storage could not be authenticated; do not deserialize it."""


def validate_secret(secret):
    if secret is not None and (not isinstance(secret, bytes) or not secret):
        raise ValueError('secret must be nonempty bytes or None')


class Integrity:
    def __init__(self, secret, system_id):
        validate_secret(secret)
        self.secret = secret
        self.system_id = system_id

    @classmethod
    def open(cls, basedir, secret, *, create=False, durability='buffered'):
        validate_secret(secret)
        filename = os.path.join(basedir, IDENTITY_FILE)
        if create:
            identity = MAGIC + os.urandom(32)
            tag = hmac.digest(secret, b'identity\x00' + identity, 'sha256')
            # Exclusive creation prevents silently replacing an existing identity.
            with open(filename, 'xb') as file:
                file.write(identity + tag)
                file.flush()
                os.fsync(file.fileno())
            if durability == 'sync':
                fileutils.sync_directory(basedir)
        try:
            with open(filename, 'rb') as file:
                data = file.read(len(MAGIC) + 32 + TAG_SIZE + 1)
        except FileNotFoundError as error:
            raise IntegrityError('Missing integrity identity; unsigned storage cannot be opened with a secret') from error
        size = len(MAGIC) + 32
        if (len(data) != size + TAG_SIZE or not data.startswith(MAGIC)
                or not hmac.compare_digest(data[size:], hmac.digest(
                    secret, b'identity\x00' + data[:size], 'sha256'))):
            raise IntegrityError('Integrity identity verification failed (wrong secret or tampered identity)')
        return cls(secret, data[len(MAGIC):size])

    def _mac(self, filename, offset, header, payload):
        # Bind to system, file kind/number, and record location, so valid
        # envelopes cannot be transplanted between systems/files/positions.
        context = (MAGIC + self.system_id + os.path.basename(filename).encode('utf-8')
                   + b'\x00' + HEADER.pack(offset) + header)
        mac = hmac.new(self.secret, context, hashlib.sha256)
        mac.update(payload)
        return mac.digest()

    def encode(self, payload, filename, offset=0):
        header = MAGIC + HEADER.pack(len(payload))
        return header + payload + self._mac(filename, offset, header, payload)

    def read(self, file, filename):
        offset = file.tell()
        header = file.read(len(MAGIC) + HEADER.size)
        if len(header) != len(MAGIC) + HEADER.size or not header.startswith(MAGIC):
            raise IntegrityError('Missing or truncated signed record header')
        size, = HEADER.unpack(header[len(MAGIC):])
        # Check available bytes before allocating using an untrusted length.
        start = file.tell()
        file.seek(0, os.SEEK_END)
        remaining = file.tell() - start
        file.seek(start)
        if size > remaining - TAG_SIZE:
            raise IntegrityError('Truncated signed record or missing HMAC tag')
        payload = file.read(size)
        tag = file.read(TAG_SIZE)
        if not hmac.compare_digest(tag, self._mac(filename, offset, header, payload)):
            raise IntegrityError('HMAC verification failed (wrong secret or tampered record)')
        return payload
