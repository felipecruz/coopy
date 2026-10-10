.. _installation:

Installation
============
Coopy requires Python 3.10 or newer. The CI test matrix covers Python
3.10–3.14 on Linux and macOS. Synchronous durability requires POSIX
directory-sync support; see :doc:`usage`.

Install into a virtual environment::

    python -m venv .venv
    . .venv/bin/activate
    python -m pip install coopy

The activation command above is for a POSIX shell. Start with the
:doc:`tutorial` after installation.

Installing from source
----------------------

To work on the current checkout, install the package in editable mode with
the test and documentation dependencies::

    git clone https://github.com/felipecruz/coopy.git
    cd coopy
    python -m venv .venv
    . .venv/bin/activate
    python -m pip install -e ".[test,docs]"

Use ``python -m pip install .`` for a non-editable source installation without
the optional test and documentation tools. See :doc:`tests` for test commands
and the local HTML documentation build.
