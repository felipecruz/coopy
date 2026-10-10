"""Domain stored in the committed legacy data-directory fixtures; keep it unchanged."""


class Notebook(object):
    def __init__(self):
        self.notes = []

    def add(self, text):
        self.notes.append(text)
        return len(self.notes)
