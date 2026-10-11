"""Domain stored in the committed format 1 clock fixture; keep it unchanged."""

from datetime import timezone


class Agenda(object):
    def __init__(self):
        self.entries = []

    def stamp(self, name):
        started = self._clock.monotonic()
        self.entries.append(
            (
                name,
                self._clock.now(),
                self._clock.utcnow(),
                self._clock.now(timezone.utc),
                self._clock.today(),
                self._clock.time(),
                self._clock.monotonic() - started,
            )
        )
