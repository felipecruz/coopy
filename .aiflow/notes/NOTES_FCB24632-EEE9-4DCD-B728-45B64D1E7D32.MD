# F19: async persistence and free-threaded readers

## Use the async facade

Use `async with coopy.AsyncPersistent(Todo, path) as todo`, then `await todo.add("milk")`. Alternatively, use `await AsyncPersistent.open(...)` and always `await todo.aclose()` in `finally`. Domain methods remain synchronous. Read through `@readonly` methods returning immutable values or detached copies. See [the concurrency guide](../../docs/concurrency.rst).

## Cancellation and shutdown

Accepted writes continue after the caller is cancelled. Do not retry blindly. Closing drains the queue and joins the writer; await close again if its waiter was cancelled, before stopping the event loop. Bound application concurrency because the queue is unbounded. Leave `group_commit_delay=0` for this facade. Direct object access and unlocked methods do not provide coherent concurrent reads.

## Validation and follow-up

Local Python 3.12/macOS: 308 tests passed; 31 skipped (30 native fork cases and the free-threaded-only assertion). Mypy, installed-wheel typing, Sphinx, Python 3.10 async replay smoke, and AIFlow roadmap validation passed.

Run the configured Python 3.13t and 3.14t jobs on Linux and macOS after pushing. Those interpreters were unavailable locally; hosted results remain unverified. The free-threaded jobs test core persistence without optional compression extensions and assert that the GIL is disabled.

Implementation commit: `091c7bac2acfebdc9ae4acb8cd34282719e8a2e2`.
