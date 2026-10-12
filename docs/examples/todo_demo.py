#!/usr/bin/env python3
"""Interactive todo-list demo that showcases coopy's persistence features.

Run with:  python docs/examples/todo_demo.py [data-directory]

The demo stores data in a directory (default: a temporary directory).
Pass a path to keep data across runs:

    python docs/examples/todo_demo.py ./my-todos

Type ``help`` at the prompt for the full command list.
"""

from __future__ import annotations

import readline  # noqa: F401 — enables arrow-key editing at the prompt
import shutil
import sys
import textwrap
from pathlib import Path
from tempfile import mkdtemp

import coopy
from coopy import fileutils
from coopy.cli import count_records, iter_actions, summarize
from coopy.decorators import readonly

# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

class TodoList:
    """A persistent todo list.  All mutating methods are journaled by coopy."""

    _clock: coopy.Clock

    def __init__(self) -> None:
        self.items: list[dict] = []
        self._next_id: int = 1

    # -- mutating -----------------------------------------------------------

    def add(self, text: str) -> int:
        item_id = self._next_id
        self.items.append({
            "id": item_id,
            "text": text,
            "done": False,
            "created": self._clock.now(),
        })
        self._next_id += 1
        return item_id

    def done(self, item_id: int) -> None:
        item = self._find(item_id)
        item["done"] = True

    def undone(self, item_id: int) -> None:
        item = self._find(item_id)
        item["done"] = False

    def delete(self, item_id: int) -> str:
        item = self._find(item_id)
        self.items.remove(item)
        return item["text"]

    def edit(self, item_id: int, text: str) -> None:
        item = self._find(item_id)
        item["text"] = text

    # -- read-only ----------------------------------------------------------

    @readonly
    def list_all(self) -> list[dict]:
        return [dict(i) for i in self.items]

    @readonly
    def list_pending(self) -> list[dict]:
        return [dict(i) for i in self.items if not i["done"]]

    @readonly
    def list_done(self) -> list[dict]:
        return [dict(i) for i in self.items if i["done"]]

    @readonly
    def search(self, query: str) -> list[dict]:
        q = query.lower()
        return [dict(i) for i in self.items if q in i["text"].lower()]

    @readonly
    def count(self) -> dict:
        total = len(self.items)
        completed = sum(1 for i in self.items if i["done"])
        return {"total": total, "done": completed, "pending": total - completed}

    # -- internal -----------------------------------------------------------

    def _find(self, item_id: int) -> dict:
        for item in self.items:
            if item["id"] == item_id:
                return item
        raise KeyError(f"No item with id {item_id}")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


USE_COLOR = supports_color()


def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if USE_COLOR else text


def print_item(item: dict) -> None:
    check = c(GREEN, "[x]") if item["done"] else c(DIM, "[ ]")
    item_id = c(YELLOW, f"#{item['id']}")
    ts = item["created"].strftime("%Y-%m-%d %H:%M")
    text = c(DIM, item["text"]) if item["done"] else item["text"]
    print(f"  {check} {item_id} {text}  {c(DIM, ts)}")


def print_items(items: list[dict], label: str = "Items") -> None:
    if not items:
        print(f"  {c(DIM, '(none)')}")
    else:
        for item in items:
            print_item(item)
    print()


def print_error(msg: str) -> None:
    print(f"  {c(RED, 'Error:')} {msg}")


def print_ok(msg: str) -> None:
    print(f"  {c(GREEN, 'OK:')} {msg}")


# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------

HELP = textwrap.dedent("""\
    {bold}Todo commands{reset}
      add <text>         Add a new item
      done <id>          Mark item as done
      undone <id>        Mark item as not done
      delete <id>        Delete an item
      edit <id> <text>   Edit an item's text
      list               List all items
      pending            List pending items
      done-list          List completed items
      search <query>     Search items by text
      count              Show item counts

    {bold}Persistence commands{reset}
      snapshot           Take a snapshot (checkpoint)
      inspect            Show data directory info
      journal            Show journal entries
      reopen             Close and reopen the system (recovery demo)

    {bold}Other{reset}
      help               Show this help
      quit / exit        Exit the demo
""")


def run_command(
    cmd: str,
    args: list[str],
    todo: TodoList,
    ctrl: coopy.base.PersistenceControl,
    basedir: Path,
) -> bool:
    """Run one command.  Returns False to exit."""
    try:
        if cmd in ("quit", "exit", "q"):
            return False

        elif cmd == "help":
            bold = BOLD if USE_COLOR else ""
            reset = RESET if USE_COLOR else ""
            print(HELP.format(bold=bold, reset=reset))

        elif cmd == "add":
            if not args:
                print_error("Usage: add <text>")
                return True
            text = " ".join(args)
            item_id = todo.add(text)
            print_ok(f"Added item #{item_id}: {text}")

        elif cmd == "done":
            item_id = _require_id(args)
            todo.done(item_id)
            print_ok(f"Marked #{item_id} as done")

        elif cmd == "undone":
            item_id = _require_id(args)
            todo.undone(item_id)
            print_ok(f"Marked #{item_id} as pending")

        elif cmd == "delete":
            item_id = _require_id(args)
            text = todo.delete(item_id)
            print_ok(f"Deleted #{item_id}: {text}")

        elif cmd == "edit":
            if len(args) < 2:
                print_error("Usage: edit <id> <new text>")
                return True
            item_id = int(args[0])
            text = " ".join(args[1:])
            todo.edit(item_id, text)
            print_ok(f"Updated #{item_id}")

        elif cmd == "list":
            print_items(todo.list_all())

        elif cmd == "pending":
            print_items(todo.list_pending())

        elif cmd in ("done-list", "completed"):
            print_items(todo.list_done())

        elif cmd == "search":
            if not args:
                print_error("Usage: search <query>")
                return True
            query = " ".join(args)
            results = todo.search(query)
            print(f"  Results for {c(BLUE, repr(query))}:")
            print_items(results)

        elif cmd == "count":
            counts = todo.count()
            print(
                f"  Total: {counts['total']}  "
                f"Pending: {c(YELLOW, str(counts['pending']))}  "
                f"Done: {c(GREEN, str(counts['done']))}"
            )
            print()

        elif cmd == "snapshot":
            ctrl.take_snapshot()
            checkpoint = fileutils.last_snapshot_file(basedir)
            print_ok(f"Snapshot saved: {checkpoint}")

        elif cmd == "inspect":
            _inspect(basedir)

        elif cmd == "journal":
            _journal(basedir)

        elif cmd == "reopen":
            return False  # signal to reopen

        else:
            print_error(f"Unknown command: {cmd!r}.  Type 'help' for commands.")

    except KeyError as exc:
        print_error(str(exc))
    except (ValueError, IndexError):
        print_error("Invalid argument.  Type 'help' for usage.")
    return True


def _require_id(args: list[str]) -> int:
    if not args:
        raise ValueError("id required")
    return int(args[0])


# ---------------------------------------------------------------------------
# Persistence inspection
# ---------------------------------------------------------------------------

def _inspect(basedir: Path) -> None:
    print(f"  {c(BOLD, 'Data directory:')} {basedir}")
    checkpoint = fileutils.last_snapshot_file(basedir)
    snapshots = fileutils.list_snapshot_files(basedir) or []
    journals = fileutils.list_log_files(basedir) or []
    print(f"  Snapshots: {len(snapshots)}")
    for name in snapshots:
        path = basedir / name
        size = path.stat().st_size
        label = " (current)" if name == checkpoint else ""
        print(f"    {name}  {size:,} bytes{label}")
    print(f"  Journals: {len(journals)}")
    for name in journals:
        path = basedir / name
        size = path.stat().st_size
        try:
            count = count_records(path, "pickle", False)
        except ValueError:
            count = "?"
        print(f"    {name}  {size:,} bytes  {count} records")
    print()


def _journal(basedir: Path) -> None:
    journals = fileutils.list_log_files(basedir) or []
    if not journals:
        print(f"  {c(DIM, '(no journal files)')}")
        print()
        return
    for name in journals:
        path = basedir / name
        print(f"  {c(BOLD, name)}")
        try:
            for _record, action in iter_actions(path, None, None):
                print(f"    {summarize(action)}")
        except Exception as exc:
            print(f"    {c(RED, f'Error reading: {exc}')}")
    print()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

BANNER = r"""
  ┌──────────────────────────────────────────┐
  │         coopy todo-list demo             │
  │                                          │
  │  Your data is fully persistent.          │
  │  Every mutating call is journaled.       │
  │  Type 'help' for commands.               │
  └──────────────────────────────────────────┘
"""


def open_system(basedir: Path) -> tuple[TodoList, coopy.base.PersistenceControl]:
    todo = coopy.open(TodoList, basedir)
    ctrl = coopy.control(todo)
    return todo, ctrl


def main() -> None:
    if len(sys.argv) > 1:
        basedir = Path(sys.argv[1])
        temp = False
    else:
        basedir = Path(mkdtemp(prefix="coopy_demo_"))
        temp = True

    print(c(BLUE, BANNER))
    print(f"  Data directory: {c(BOLD, str(basedir))}")
    if temp:
        print(f"  {c(DIM, '(temporary — pass a path argument to persist across runs)')}")
    print()

    todo, ctrl = open_system(basedir)
    report = ctrl.recovery_report
    if report.replayed > 0:
        print(f"  Recovered: replayed {report.replayed} actions from journal")
        print()

    reopen = False
    try:
        while True:
            try:
                line = input(c(GREEN, "todo> ")).strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            parts = line.split()
            cmd, args = parts[0].lower(), parts[1:]
            result = run_command(cmd, args, todo, ctrl, basedir)
            if not result:
                if cmd == "reopen":
                    reopen = True
                break
    except KeyboardInterrupt:
        print()
    finally:
        ctrl.close(snapshot=True)

    if reopen:
        print()
        print(f"  {c(YELLOW, 'Closing and reopening...')}")
        print()
        todo, ctrl = open_system(basedir)
        report = ctrl.recovery_report
        print_ok(
            f"Reopened.  Checkpoint: {report.checkpoint or 'none'}, "
            f"replayed {report.replayed} actions."
        )
        counts = todo.count()
        print(
            f"  Recovered state: {counts['total']} items "
            f"({counts['pending']} pending, {counts['done']} done)"
        )
        print()
        try:
            while True:
                try:
                    line = input(c(GREEN, "todo> ")).strip()
                except EOFError:
                    print()
                    break
                if not line:
                    continue
                parts = line.split()
                cmd, args = parts[0].lower(), parts[1:]
                if cmd == "reopen":
                    print_error("Already reopened once in this session.")
                    continue
                if not run_command(cmd, args, todo, ctrl, basedir):
                    break
        except KeyboardInterrupt:
            print()
        finally:
            ctrl.close(snapshot=True)

    if temp:
        shutil.rmtree(basedir, ignore_errors=True)
        print(f"  {c(DIM, 'Temporary data directory removed.')}")

    print(f"  {c(DIM, 'Goodbye!')}")


if __name__ == "__main__":
    main()
