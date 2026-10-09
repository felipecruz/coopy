"""Importable domain shared by the maintained documentation examples."""

from coopy.decorators import abort_exception, readonly


class Wiki:
    def __init__(self):
        self.pages = {}

    @abort_exception
    def create_page(self, page_id, content):
        # Validate before mutating: abort_exception does not roll back state.
        if page_id in self.pages:
            raise ValueError("Page already exists")
        self.pages[page_id] = {
            "content": content,
            "modified": self._clock.now(),
            "utc_modified": self._clock.utcnow(),
            "day": self._clock.today(),
        }

    @readonly
    def get_page(self, page_id):
        # All values are immutable; returning a copy prevents mutable escape.
        return dict(self.pages[page_id])
