"""Generated command histories must recover exactly the acknowledged live state."""

from copy import deepcopy
from tempfile import TemporaryDirectory

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule, run_state_machine_as_test

import coopy
from coopy.decorators import abort_exception, readonly


class Ledger:
    def __init__(self):
        self.values = {}
        self.events = []

    def put(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)

    def add(self, key, *, amount):
        self.values[key] = self.values.get(key, 0) + amount

    def record_time(self, label):
        self.events.append((label, self._clock.now(), self._clock.utcnow(), self._clock.today()))

    @abort_exception
    def require_positive(self, key, value):
        if value <= 0:
            raise ValueError("positive values only")
        self.values[key] = value

    @readonly
    def read(self):
        return deepcopy((self.values, self.events))


def restore_ledger(state):
    ledger = Ledger()
    ledger.__dict__.update(state)
    return ledger


keys = st.sampled_from(["a", "b", "c", "", "☕"])
values = st.integers(min_value=-1000, max_value=1000)


class PersistenceMachine(RuleBasedStateMachine):
    def __init__(self, codec, durability, secret):
        super().__init__()
        self.directory = TemporaryDirectory(prefix="coopy-property-")
        registry = coopy.TypeRegistry()
        registry.register("ledger", Ledger, encode=vars, decode=restore_ledger)
        self.options = dict(
            serializer=coopy.JsonSerializer(registry)
            if codec == "json"
            else coopy.PickleSerializer(),
            durability=durability,
            secret=secret,
        )
        self.expected = {}
        self.events = []
        self.proxy = self.open()

    def open(self):
        proxy = coopy.open(Ledger, self.directory.name, **self.options)
        # Exercise journal rotation as well as checkpoint boundaries.
        proxy.publisher.subscribers[0].file.max_size = 256
        return proxy

    @rule(key=keys, value=values)
    def put(self, key, value):
        self.proxy.put(key, value)
        self.expected[key] = value

    @rule(key=keys)
    def remove(self, key):
        self.proxy.remove(key)
        self.expected.pop(key, None)

    @rule(key=keys, amount=values)
    def add(self, key, amount):
        self.proxy.add(key, amount=amount)
        self.expected[key] = self.expected.get(key, 0) + amount

    @rule(key=keys, value=values)
    def guarded_call(self, key, value):
        if value <= 0:
            with pytest.raises(ValueError, match="positive values only"):
                self.proxy.require_positive(key, value)
        else:
            self.proxy.require_positive(key, value)
            self.expected[key] = value

    @rule(label=st.text(max_size=20))
    def record_time(self, label):
        self.proxy.record_time(label)
        self.events.append(self.proxy.read()[1][-1])

    @rule()
    def snapshot(self):
        coopy.control(self.proxy).take_snapshot()

    @rule()
    def restart(self):
        live = self.proxy.read()
        coopy.control(self.proxy).close()
        self.proxy = self.open()
        assert self.proxy.read() == live == (self.expected, self.events)

    @invariant()
    def agrees_with_model(self):
        assert self.proxy.read() == (self.expected, self.events)

    def teardown(self):
        try:
            # Even histories with no generated restart must recover their tail.
            self.restart()
        finally:
            try:
                coopy.control(self.proxy).close()
            finally:
                self.directory.cleanup()


@pytest.mark.parametrize("codec", ["pickle", "json"])
@pytest.mark.parametrize("durability", ["buffered", "sync"])
@pytest.mark.parametrize("secret", [None, b"property-test-key"], ids=["unsigned", "signed"])
def test_generated_persistence_histories(codec, durability, secret):
    run_state_machine_as_test(
        lambda: PersistenceMachine(codec, durability, secret),
        settings=settings(max_examples=30, stateful_step_count=35, deadline=None),
    )
