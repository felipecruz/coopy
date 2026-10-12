Development checks
==================

Install the development, test, documentation, and compression dependencies::

    python -m pip install -e ".[dev,test,docs,zstd,lz4]"
    pre-commit install

Run the same lint and formatting checks as CI::

    python -m ruff check .
    python -m ruff format --check .
    pre-commit run --all-files

``make lint`` checks both; ``make format`` applies safe lint fixes and formatting.
Ruff is pinned to the same version in the dev extra and pre-commit configuration;
update both pins together. Lint covers Python sources, tests, scripts and docs
examples, using Pyflakes, import sorting, and Ruff's default pycodestyle rules.
See the `Ruff integration documentation`_.

Type checks
-----------

The installed public-API check disables build isolation, so install its build
prerequisites first. Then run both checks, as in CI::

    python -m pip install "setuptools>=77" wheel
    python -m mypy
    python scripts/check_typing.py

The script builds and installs the checkout into a temporary directory
and runs strict mypy against ``tests/typing/public_api.py`` outside the source
tree. It checks that the installed package includes ``py.typed``.

Generated persistence histories
-------------------------------

The full pytest suite includes Hypothesis state machines. Run them alone with::

    python -m pytest tests/functional/test_properties.py --hypothesis-show-statistics

Each of eight serializer/durability/signing combinations generates 30 histories
of up to 35 steps. Commands include replacement, deletion, keyword-argument
increments, successful/failed abort-decorated calls, recorded clocks, snapshots,
and close/reopen. Small journal limits exercise rotation. An independent model
checks every step; each restart compares restored state with a deep copy of live
state, and teardown always checks final recovery. Every example gets fresh
temporary storage, also during shrinking. Hypothesis retains failing examples
in its local ``.hypothesis`` database; use ``--hypothesis-seed=N`` to reproduce a
seeded run. See `Hypothesis stateful testing`_.

These are sequential clean-restart properties, not power-loss or concurrent
execution simulations. The separate fault-injection, concurrency, subprocess,
and native-fork tests remain in the full suite.

Coverage policy
---------------

The baseline is **93% line coverage** of the entire ``coopy`` package, enforced
by ``tool.coverage.report.fail_under`` in ``pyproject.toml``. No package modules
are omitted, including legacy networking, bundled test helpers and platform
specific fork code. This is line coverage, not branch or subprocess coverage.

Measurement on 2026-10-10, before the tooling migration: Python 3.12.2/macOS,
308 passed and 31 skipped, **1,748 of 1,879 statements (93.0282%)**. The threshold
rounds that measurement down to a whole percent. Skips comprise 30 native Linux
fork scenarios and the assertion requiring a free-threaded interpreter. Optional
zstd and lz4 dependencies were installed. Reproduce the CI gate with::

    python -m pytest -W error::DeprecationWarning --cov=coopy --cov-report=term-missing --cov-report=xml

After formatting, stateful properties, and malformed-storage regression tests,
the same environment passed 329 tests with 31 skips: **1,747 of 1,873 statements
(93.27%)**. The gate was also verified to fail an intentionally under-covered
run. Small variations are possible in timing-dependent network cleanup paths.

The environment must permit local sockets. Ordinary Linux/macOS Python
3.10–3.14 jobs enforce this floor; free-threaded jobs run the properties and suite
without coverage or optional compression extensions. Coverage below the floor
fails pytest. Raise the baseline when sustained improvements justify it; do not
lower it or omit modules merely to pass CI. This fixed floor prevents regression
below the baseline; it does not automatically ratchet upward on each commit.

Each regular test job uploads ``coverage.xml`` to `Codecov`_, flagged by Python
version and OS. Codecov merges the uploads, keeps the history, and comments on
pull requests. ``codecov.yml`` makes the project status fail on a drop of more
than 0.5% from the base commit; patch coverage is reported but does not block.

Generated reference and dependency updates
------------------------------------------

Sphinx uses its built-in `autodoc`_ and `autosummary`_ extensions to generate
:doc:`api` from runtime signatures, overloads, type hints and docstrings. Generated
RST pages in ``docs/_generated`` are ignored by Git and recreated during builds.
Public controls, async calls, decorators, serializers, recovery records and errors
are covered; undocumented dynamic domain methods remain application-specific.

Build from scratch with warnings treated as errors::

    python -m sphinx -W --keep-going -E -a -b html docs build/docs

Open ``build/docs/api.html``. CI requires lint, tests, free-threaded checks, and
the documentation build before producing release distributions.

``.github/dependabot.yml`` schedules weekly updates for the ``github-actions``
ecosystem at the repository root, following the `GitHub configuration guide`_.
GitHub evaluates updates after the configuration reaches the default branch;
review and merge the resulting pull requests normally.

.. _Ruff integration documentation: https://docs.astral.sh/ruff/integrations/
.. _Hypothesis stateful testing: https://hypothesis.readthedocs.io/en/latest/stateful.html
.. _Codecov: https://app.codecov.io/gh/felipecruz/coopy
.. _autodoc: https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
.. _autosummary: https://www.sphinx-doc.org/en/master/usage/extensions/autosummary.html
.. _GitHub configuration guide: https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/auto-update-actions
