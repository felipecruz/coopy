.. _tests:

Tests
-----

Install the optional test dependencies from the repository root, using your
virtual environment's Python::

    python -m pip install -e ".[test]"

Run the suite with the same deprecation-warning policy as CI::

    python -m pytest --verbose -W error::DeprecationWarning

The suite includes local socket tests, so the environment must permit binding
and connecting to local ports. CI runs on Linux and macOS with Python 3.10–3.14.
A local run verifies only the interpreter and platform used for that run.
Install ``.[test,zstd,lz4]`` to include both optional compression codecs, as in
the regular CI jobs. See :doc:`development` for lint, typing and coverage gates.

``make test`` also runs pytest, but first invokes ``make clean``, which removes
build outputs, coverage reports, package metadata, bytecode, and coopy logs.
Use the direct pytest command above to keep existing artifacts.

Coverage report
---------------

Generate an HTML report for the current checkout::

    python -m pytest --cov-report html --cov coopy

Open ``htmlcov/index.html``. For a terminal report instead, run::

    python -m pytest --cov coopy

``make coverage`` is equivalent to the HTML report command. Coverage figures
depend on the current code and tests; generate a fresh report when needed.

Maintained documentation examples
---------------------------------

Install the test and documentation dependencies from the repository root::

    python -m pip install -e ".[test,docs]"

Execute the sources included in the guide and build HTML with warnings treated
as errors::

    python -m pytest tests/functional/test_documentation.py
    python -m sphinx -W --keep-going -E -a -b html docs build/docs

The examples run in subprocesses with temporary working and data directories.
They cover close/reopen, checkpoint plus journal recovery, all recorded clock
methods, readonly copies, decorator failures, and experimental replication.
They also exercise snapshot-state migration and recorded random values.
A separate process also reopens the tutorial's importable domain. The replication
example needs local socket access. F13 acceptance tests additionally cover
concurrent catch-up with recorded clocks, fragmented and interrupted packets,
authentication rejection, shutdown guards, and explicit reconnect.
CI runs these tests and the Sphinx build. The generated guide is at
``build/docs/index.html``.
