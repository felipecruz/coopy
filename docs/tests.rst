.. _tests:

Tests
-----

First time::

    pip install -e ".[test]"

To actually run the tests::

    make test

Coverage Report
---------------

First time::

    pip install -e ".[test]"

And then::

    make coverage

Coverage report::

    $ python -m pytest --cov coopy

    Name                           Stmts   Miss  Cover
    --------------------------------------------------
    coopy/__init__                     0      0   100%
    coopy/base                       135     17    87%
    coopy/decorators                   9      0   100%
    coopy/error                        3      0   100%
    coopy/fileutils                  125      5    96%
    coopy/foundation                  71      8    89%
    coopy/journal                     30      2    93%
    coopy/network/__init__             1      0   100%
    coopy/network/default_select     192     56    71%
    coopy/network/linux_epoll          0      0   100%
    coopy/network/network             42     10    76%
    coopy/network/osx_kqueue           0      0   100%
    coopy/restore                     42      6    86%
    coopy/snapshot                    45      3    93%
    coopy/utils                        9      0   100%
    coopy/validation                  45      1    98%
    --------------------------------------------------
    TOTAL                            749    108    86%

Maintained documentation examples
---------------------------------

Install the test and documentation dependencies from the repository root::

    python -m pip install -e ".[test,docs]"

Execute the sources included in the guide and build HTML with warnings treated
as errors::

    python -m pytest tests/functional/test_documentation.py
    python -m sphinx -W --keep-going -b html docs build/docs

The examples run in subprocesses with temporary working and data directories.
They cover close/reopen, checkpoint plus journal recovery, all recorded clock
methods, readonly copies, decorator failures, and experimental replication.
A separate process also reopens the tutorial's importable domain. The replication
example needs local socket access. F13 acceptance tests additionally cover
concurrent catch-up with recorded clocks, fragmented and interrupted packets,
authentication rejection, shutdown guards, and explicit reconnect.
CI runs these tests and the Sphinx build. The generated guide is at
``build/docs/index.html``.
