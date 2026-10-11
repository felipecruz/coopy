"""Run with: python docs/examples/raffle.py"""

from tempfile import TemporaryDirectory
from uuid import UUID

import coopy


class Raffle:
    _env: coopy.Env  # injected by coopy

    def __init__(self) -> None:
        self.entrants: list[str] = []
        self.tickets: dict[UUID, str] = {}
        self.winner: str | None = None

    def enter(self, name: str) -> UUID:
        ticket = self._env.uuid4()
        self.entrants.append(name)
        self.tickets[ticket] = name
        return ticket

    def draw(self) -> str:
        self.winner = self._env.choice(self.entrants)
        return self.winner


def round_trip(directory):
    with coopy.control(coopy.open(Raffle, basedir=directory)) as raffle:
        ticket = raffle.enter("ana")
        raffle.enter("bo")
        raffle.enter("cy")
        winner = raffle.draw()

    # Replay returns the recorded UUIDs and the recorded choice.
    with coopy.control(coopy.open(Raffle, basedir=directory)) as raffle:
        assert raffle.tickets[ticket] == "ana"
        assert raffle.winner == winner


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        round_trip(directory)
