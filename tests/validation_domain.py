"""Fixtures for source validation: one domain per non-deterministic pattern."""

import datetime
import os
import random
import secrets
import time
import uuid
from datetime import date
from datetime import datetime as dt
from random import randint as roll
from time import time as epoch

from coopy import Clock, Env


class AliasedNow:
    def run(self):
        return dt.now()


class AliasedUtcnow:
    def run(self):
        return dt.utcnow()


class QualifiedNow:
    def run(self):
        return datetime.datetime.now()


class QualifiedToday:
    def run(self):
        return datetime.date.today()


class DateToday:
    def run(self):
        return date.today()


class TimeTime:
    def run(self):
        return time.time()


class ImportedTime:
    def run(self):
        return epoch()


class Monotonic:
    def run(self):
        return time.monotonic()


class RandomRandom:
    def run(self):
        return random.random()


class RandomGauss:
    def run(self):
        return random.gauss(0, 1)


class AliasedRandint:
    def run(self):
        return roll(1, 6)


class Uuid4:
    def run(self):
        return uuid.uuid4()


class Urandom:
    def run(self):
        return os.urandom(16)


class SecretsToken:
    def run(self):
        return secrets.token_hex()


class SecretsChoice:
    def run(self):
        return secrets.choice("abc")


class LocalImport:
    def run(self):
        from uuid import uuid4 as make_id

        return make_id()


class Nested:
    def run(self, items):
        return items[0].append(str(dt.now()))


PATTERNS = {
    AliasedNow: ("dt.now", "datetime.datetime.now", "self._clock.now()"),
    AliasedUtcnow: ("dt.utcnow", "datetime.datetime.utcnow", "self._clock.utcnow()"),
    QualifiedNow: ("datetime.datetime.now", "datetime.datetime.now", "self._clock.now()"),
    QualifiedToday: ("datetime.date.today", "datetime.date.today", "self._clock.today()"),
    DateToday: ("date.today", "datetime.date.today", "self._clock.today()"),
    TimeTime: ("time.time", "time.time", "self._clock.time()"),
    ImportedTime: ("epoch", "time.time", "self._clock.time()"),
    Monotonic: ("time.monotonic", "time.monotonic", "self._clock.monotonic()"),
    RandomRandom: ("random.random", "random.random", "self._env.random()"),
    RandomGauss: ("random.gauss", "random.gauss", "pass the value as a method argument"),
    AliasedRandint: ("roll", "random.randint", "self._env.randint()"),
    Uuid4: ("uuid.uuid4", "uuid.uuid4", "self._env.uuid4()"),
    Urandom: ("os.urandom", "os.urandom", "self._env.token_bytes()"),
    SecretsToken: ("secrets.token_hex", "secrets.token_hex", "self._env.token_hex()"),
    SecretsChoice: ("secrets.choice", "secrets.choice", "self._env.choice()"),
    LocalImport: ("make_id", "uuid.uuid4", "self._env.uuid4()"),
    Nested: ("dt.now", "datetime.datetime.now", "self._clock.now()"),
}


class Deterministic:
    _clock: Clock
    _env: Env

    def __init__(self):
        self.items = []

    def add(self, name):
        stamp = self._clock.now(datetime.timezone.utc)
        self.items.append(
            (
                name,
                stamp,
                self._clock.time(),
                self._clock.monotonic(),
                self._env.random(),
                self._env.randint(1, 6),
                self._env.uuid4(),
                self._env.token_hex(),
                random.Random(7).random(),
                dt(2024, 1, 1),
                date.fromisoformat("2024-01-01"),
                "".join([]),
            )
        )
