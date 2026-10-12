"""The example on the front page of the documentation."""

import tempfile

import coopy
from coopy.decorators import readonly


class Bank:
    """Plain Python: no base class, no ORM, no schema."""

    _clock: coopy.Clock  # injected by coopy

    def __init__(self) -> None:
        self.accounts: dict[str, int] = {}
        self.history: list[tuple[str, str, int]] = []

    def deposit(self, name: str, amount: int) -> None:
        self.accounts[name] = self.accounts.get(name, 0) + amount
        self.history.append((self._clock.now().isoformat(), name, amount))

    def transfer(self, source: str, target: str, amount: int) -> None:
        if self.accounts.get(source, 0) < amount:
            raise ValueError("insufficient funds")
        self.accounts[source] -= amount
        self.accounts[target] = self.accounts.get(target, 0) + amount

    @readonly
    def balance(self, name: str) -> int:
        return self.accounts.get(name, 0)


data = tempfile.mkdtemp()

# First run: every method call is appended to a journal on disk.
with coopy.control(coopy.open(Bank, data)) as bank:
    bank.deposit("alice", 100)
    bank.transfer("alice", "bob", 30)
    print(bank.balance("alice"), bank.balance("bob"))  # 70 30

# Later (a restart, a crash, a deploy): the same object comes back.
with coopy.control(coopy.open(Bank, data)) as bank:
    print(bank.balance("alice"), bank.balance("bob"))  # 70 30
    print(coopy.control(bank).recovery_report.replayed, "calls replayed")  # 2 calls replayed
