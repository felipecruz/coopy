.. _tests:

Tests
-----

First time::

    pip install -r requirements.txt

To actually run the tests::

    make test

Coverage Report
---------------

First time::

    pip install -r requirements.txt

And then::

    make coverage

Coverage report::

    $ py.test --cov coopy

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
