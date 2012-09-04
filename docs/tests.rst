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
    coopy/base                       135     18    87%
    coopy/decorators                   9      0   100%
    coopy/fileutils                  117      5    96%
    coopy/foundation                  42      3    93%
    coopy/journal                     30      2    93%
    coopy/network/__init__             1      0   100%
    coopy/network/default_select     192     56    71%
    coopy/network/network             42     10    76%
    coopy/restore                     42      6    86%
    coopy/snapshot                    45      3    93%
    coopy/utils                        9      0   100%
    --------------------------------------------------
    TOTAL                            664    103    84%
