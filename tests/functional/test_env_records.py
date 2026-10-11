"""self._env records random numbers, UUIDs and tokens for replay (F39)."""

import struct
import uuid
from datetime import datetime

import pytest

import coopy
from coopy.base import CoopyProxy, init_persistent_system
from coopy.cli import summarize
from coopy.environment import RecordEnv, RestoreEnv
from coopy.error import ClockDivergenceError
from coopy.foundation import Action, RecordClock, RestoreClock
from coopy.network.network import COPYNET_HEADER, prepare_data
from coopy.restore import RecoveryError
from coopy.testing import FrozenClock, SeededEnv, install_clock, install_env
from coopy.validation import validate_date_datetime_calls
from tests.functional.test_clock_records import journal_actions
from tests.unit.test_network_select import fake_master as fake_master
from tests.unit.test_network_select import wait_for

CALLS = [
    "randint",
    "choice",
    "shuffle",
    "sample",
    "random",
    "uniform",
    "time",
    "uuid4",
    "token_bytes",
    "token_hex",
    "token_urlsafe",
]


class Player:
    def __init__(self, name):
        self.name = name
        self.score = 0


class Game:
    _clock: coopy.Clock
    _env: coopy.Env

    def __init__(self):
        self.players = [Player("ana"), Player("bo"), Player("cy")]
        self.rounds = []

    def play(self):
        roll = self._env.randint(1, 6)
        # the domain's own player object, also after replay
        self._env.choice(self.players).score += roll
        order = list(self.players)
        self._env.shuffle(order)
        picked = self._env.sample(self.players, 2)
        self.rounds.append(
            (
                roll,
                [p.name for p in order],
                [p.name for p in picked],
                self._env.random(),
                self._env.uniform(-1.0, 1.0),
                self._clock.time(),
                self._env.uuid4(),
                self._env.token_bytes(8),
                self._env.token_hex(),
                self._env.token_urlsafe(12),
            )
        )

    def state(self):
        return [(p.name, p.score) for p in self.players], list(self.rounds)


def decode_object(cls):
    def decode(state):
        obj = object.__new__(cls)
        obj.__dict__.update(state)
        return obj

    return decode


def json_serializer():
    registry = coopy.TypeRegistry()
    registry.register("game", Game, encode=lambda g: dict(vars(g)), decode=decode_object(Game))
    registry.register(
        "player", Player, encode=lambda p: dict(vars(p)), decode=decode_object(Player)
    )
    registry.register("uuid", uuid.UUID, encode=str, decode=uuid.UUID)
    return coopy.JsonSerializer(registry)


def assert_round_types(rounds):
    for roll, order, picked, number, spread, _, ident, raw, hexed, safe in rounds:
        assert 1 <= roll <= 6 and sorted(order) == ["ana", "bo", "cy"] and len(picked) == 2
        assert 0.0 <= number < 1.0 and -1.0 <= spread <= 1.0
        assert type(ident) is uuid.UUID and ident.version == 4
        assert len(raw) == 8 and len(hexed) == 64 and len(safe) == 16


@pytest.mark.parametrize("make_serializer", [coopy.PickleSerializer, json_serializer])
@pytest.mark.parametrize("snapshot", [False, True])
def test_every_source_replays_after_restart(tmp_path, make_serializer, snapshot):
    serializer = make_serializer()
    with coopy.control(coopy.open(Game, basedir=str(tmp_path), serializer=serializer)) as game:
        for _ in range(3):
            game.play()
        if snapshot:
            coopy.control(game).take_snapshot()
        game.play()
        live = game.state()
        # _env exists only during a call, so it never reaches snapshots
        assert "_env" not in vars(coopy.control(game)._proxy.obj)
    assert_round_types(live[1])
    assert sum(score for _, score in live[0]) == sum(r[0] for r in live[1])

    with coopy.control(coopy.open(Game, basedir=str(tmp_path), serializer=serializer)) as game:
        assert game.state() == live
        assert "_env" not in vars(coopy.control(game)._proxy.obj)

    (record, *_) = journal_actions(
        tmp_path, None if make_serializer is coopy.PickleSerializer else serializer
    )
    assert [method for method, _ in record.results] == CALLS


def test_seeded_env_gives_exact_values_that_replay(tmp_path):
    with coopy.control(coopy.open(Game, basedir=str(tmp_path))) as game:
        install_env(game, SeededEnv(42))
        install_clock(game, FrozenClock(datetime(2026, 1, 1, 12)))
        game.play()
        game.play()
        seeded = game.state()
    with coopy.control(coopy.open(Game, basedir=str(tmp_path / "again"))) as game:
        install_env(game, SeededEnv(42))
        install_clock(game, FrozenClock(datetime(2026, 1, 1, 12)))
        game.play()
        game.play()
        assert game.state() == seeded
        install_env(game, None)
        game.play()
        assert game.state()[1][:2] == seeded[1]
    with coopy.control(coopy.open(Game, basedir=str(tmp_path))) as game:
        assert game.state() == seeded


def test_seeded_env_matches_random_for_numbers():
    env, rng = SeededEnv("seed"), __import__("random").Random("seed")
    assert [env.random(), env.randint(1, 100)] == [rng.random(), rng.randint(1, 100)]
    assert SeededEnv(1).uuid4() == SeededEnv(1).uuid4() != SeededEnv(2).uuid4()
    assert SeededEnv(1).uuid4().version == 4
    assert len(SeededEnv().token_bytes()) == 32 and SeededEnv().token_bytes(0) == b""
    tokens = SeededEnv(3)
    assert len(tokens.token_hex(5)) == 10 and len(tokens.token_urlsafe(5)) == 7


def test_install_env_on_plain_domain():
    game = Game()
    install_env(game, SeededEnv(7))
    assert game._env.randint(1, 6) == SeededEnv(7).randint(1, 6)
    install_env(game, None)
    assert 1 <= game._env.randint(1, 6) <= 6


def test_replica_replays_env_values(fake_master):  # noqa: F811
    proxy, slave, peer = fake_master
    source = CoopyProxy(Game(), [])
    source.play()
    action = Action(1, "play", datetime(2020, 1, 1), (), {})
    action.results = list(source.obj._clock.results)
    action.raised = False
    for value in (Game(), action):
        header, payload = prepare_data(value)
        peer.sendall(header + payload)
    peer.sendall(struct.pack(COPYNET_HEADER, 0, b"r"))
    assert slave.wait_until_synchronized(3)
    wait_for(lambda: len(proxy.obj.rounds) == 1)
    assert proxy.obj.state() == source.obj.state()
    assert "_env" not in vars(proxy.obj)
    source.close()


def test_replica_unsynchronizes_on_env_divergence(fake_master):  # noqa: F811
    proxy, slave, peer = fake_master
    action = Action(1, "play", datetime(2020, 1, 1), (), {})
    action.results = [("randint", 9)]
    action.raised = False
    for value in (Game(), action):
        header, payload = prepare_data(value)
        peer.sendall(header + payload)
    peer.sendall(struct.pack(COPYNET_HEADER, 0, b"r"))
    wait_for(lambda: slave.error is not None)
    assert "randint() returning 9" in slave.error and "randint(1, 6)" in slave.error
    assert not slave.synchronized


def restore_env(results):
    return RestoreEnv(RestoreClock(results, "act"))


# (recorded entries, call on RestoreEnv, expected text, actual text)
DIVERGENT = {
    "out of range": (
        [("randint", 9)],
        lambda e: e.randint(1, 6),
        "randint() returning 9",
        "randint(1, 6)",
    ),
    "other method": (
        [("random", 0.5)],
        lambda e: e.uniform(0, 1),
        "random() returning 0.5",
        "uniform(0, 1)",
    ),
    "clock value": (
        [("now", datetime(2026, 1, 1))],
        lambda e: e.random(),
        "now() returning",
        "random()",
    ),
    "legacy bare value": ([0.5], lambda e: e.random(), "time() or monotonic()", "random()"),
    "too many calls": ([], lambda e: e.uuid4(), "no call (0 recorded)", "uuid4()"),
    "index too big": (
        [("choice", 3)],
        lambda e: e.choice("abc"),
        "choice() returning 3",
        "choice(<3 items>)",
    ),
    "short sample": (
        [("sample", [0])],
        lambda e: e.sample("abc", 2),
        "sample() returning [0]",
        "sample(<3 items>, 2)",
    ),
    "not a permutation": (
        [("shuffle", [0, 0])],
        lambda e: e.shuffle([1, 2]),
        "shuffle()",
        "shuffle(<2 items>)",
    ),
    "bad uuid": ([("uuid4", "nope")], lambda e: e.uuid4(), "uuid4() returning 'nope'", "uuid4()"),
    "token size": (
        [("token_hex", "ab")],
        lambda e: e.token_hex(8),
        "token_hex() returning <redacted 2 chars>",
        "token_hex(8)",
    ),
    "bytes size": (
        [("token_bytes", b"x")],
        lambda e: e.token_bytes(),
        "token_bytes() returning <redacted 1 bytes>",
        "token_bytes(None)",
    ),
}


@pytest.mark.parametrize("case", DIVERGENT)
def test_divergent_env_calls_raise(case):
    results, call, expected, actual = DIVERGENT[case]
    env = restore_env(results)
    with pytest.raises(ClockDivergenceError) as caught:
        call(env)
    assert caught.value.expected.startswith(expected)
    assert caught.value.actual == actual
    # the divergence sticks even if the domain swallowed it
    with pytest.raises(ClockDivergenceError):
        env._clock.check_calls()


def test_recorded_secret_never_appears_in_messages():
    env = restore_env([("token_urlsafe", "s3cr3t-value")])
    with pytest.raises(ClockDivergenceError) as caught:
        env.token_urlsafe(4)
    assert "s3cr3t" not in str(caught.value)
    action = Action(1, "issue", datetime(2026, 1, 1), (), {})
    action.results = [("token_hex", "deadbeef"), ("randint", 4)]
    line = summarize(action)
    assert "deadbeef" not in line and "token_hex=<redacted 8 chars>" in line
    assert "randint=4" in line


def test_restore_env_returns_recorded_values():
    players = ["a", "b", "c"]
    env = restore_env(
        [
            ("choice", 2),
            ("shuffle", [2, 0, 1]),
            ("sample", [1, 2]),
            ("uuid4", "cd613e30-d8f1-4adf-91b7-584a2265b1f5"),
            ("token_urlsafe", "QRAnxNE"),
        ]
    )
    assert env.choice(players) == "c"
    env.shuffle(players)
    assert players == ["c", "a", "b"]
    assert env.sample(players, 2) == ["a", "b"]
    assert env.uuid4() == uuid.UUID("cd613e30-d8f1-4adf-91b7-584a2265b1f5")
    assert env.token_urlsafe(5) == "QRAnxNE"
    env._clock.check_complete()


def test_record_env_records_positions_and_rejects_empty_choice():
    clock = RecordClock()
    env = RecordEnv(clock, SeededEnv(5))
    items = ["x", "y", "z"]
    chosen = env.choice(items)
    assert clock.results == [("choice", items.index(chosen))]
    with pytest.raises(IndexError):
        env.choice([])
    assert len(clock.results) == 1


def test_strict_recovery_and_salvage_report_env_divergence(tmp_path, monkeypatch):
    with coopy.control(coopy.open(Game, basedir=str(tmp_path))) as game:
        game.play()

    def changed(self):
        # a code change: replay rolls a smaller die and stops early
        self._env.randint(1, 2)

    monkeypatch.setattr(Game, "play", changed)
    with pytest.raises(RecoveryError) as caught:
        init_persistent_system(Game, str(tmp_path), recovery="strict")
    assert isinstance(caught.value.__cause__, ClockDivergenceError)
    assert caught.value.report.stop.kind == "clock"
    result = init_persistent_system(Game, str(tmp_path), recovery="salvage")
    assert result.report.stop.kind == "clock" and result.report.replayed == 0


def test_validation_accepts_env_calls():
    source = "def play(self):\n    return self._env.randint(1, 6), self._clock.now()\n"
    assert validate_date_datetime_calls(source)
