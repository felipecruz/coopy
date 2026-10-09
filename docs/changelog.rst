.. _changelog:

Changelog
=========

0.5.0
-----

* Python 3.10+ only. Dropped Python 2 and the ``six`` dependency.
* Packaging moved to ``pyproject.toml``; CI moved to GitHub Actions, with
  PyPI publishing on version tags.
* Importing coopy no longer creates ``coopy.log``; the log file is set up by
  ``init_persistent_system``.
* Restore logs actions that fail on replay but succeeded originally as errors,
  and reports truncated or corrupted journal files.
* ``start_snapshot_manager`` no longer blocks the caller.
* ``shutdown()`` now closes the master server.
* Fixed master/slave replication on Python 3 (bytes handling, slave
  start-up, partial reads, clock replay on slaves).
* ``RotateFileWrapper.flush()`` works again.
* Writes no longer fail after ``start_master()`` (the master server now
  implements the full subscriber interface).
* ``validate_system`` skips methods whose source is unavailable (REPL,
  ``exec``) instead of crashing.
