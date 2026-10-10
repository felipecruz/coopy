"""Current TodoList; tests/fixtures/state/todo_v1 holds its unversioned 0.6.0 shape.

Version 1 (0.6.0): ``items`` is a list of strings.
Version 2: ``items`` holds ``{"text", "done"}`` dictionaries.
Version 3: ``items`` is renamed ``tasks`` and a ``title`` is added.
"""


class TodoList:
    __coopy_version__ = 3

    def __init__(self):
        self.title = "Todo"
        self.tasks = []

    def add(self, text):
        self.tasks.append({"text": text, "done": False})

    def complete(self, text):
        for task in self.tasks:
            if task["text"] == text:
                task["done"] = True


def strings_to_dicts(todo):
    todo.items = [{"text": text, "done": False} for text in todo.items]
    return todo


def rename_items(todo):
    todo.tasks = todo.__dict__.pop("items")
    todo.title = "Todo"
    return todo
