Command-line tool
=================

``python -m coopy`` inspects and maintains data directories without writing
Python code. Every command takes the directory's writer lock (see :doc:`usage`)
for as long as it runs, so it fails with ``already open for writing`` while an
application has the directory open. Errors print ``coopy: error: ...`` and exit
with status 1; invalid arguments exit with status 2.

.. warning::

   ``verify``, ``log``, ``snapshot`` and ``convert`` load stored data. With the
   default pickle serializer that **unpickles** it, which can run arbitrary
   code: use them only on trusted directories. The modules defining your
   domain classes must be importable, so add them to ``PYTHONPATH``. These
   commands print this notice on standard error. ``inspect`` and ``prune``
   decode nothing.

Commands
--------

``inspect DIR``
    Prints the format manifest (``coopy.json``), the current checkpoint, every
    checkpoint and journal with its size, and how many actions each journal
    holds. Records are counted from pickle opcodes, JSON lines or signed
    envelopes without decoding them; signed records are not verified (use
    ``verify``). A truncated journal is reported as ``DAMAGED`` and the command
    exits with status 1.

``verify DIR``
    Runs strict recovery in memory, writing nothing, and prints the number of
    replayed actions. Exits with status 1 when recovery stops.

``log DIR [--after-checkpoint]``
    Lists every journaled action in order: record number, call time, method
    name, a shortened argument summary, ``[raised]`` for actions that failed
    when they ran, and recorded clock values. Signed records are verified
    before they are decoded.

``snapshot DIR CLASS``
    Opens ``DIR`` with ``CLASS`` (``module:QualName``), replays its journal,
    writes a new checkpoint and closes it. ``--compression zstd|lz4`` compresses
    the new checkpoint. ``DIR`` must already hold a checkpoint.

``prune DIR --keep N [--keep-for DURATION]``
    Runs ``coopy.prune`` (see :doc:`snapshots`): deletes checkpoints older than
    the newest ``N`` and outside ``DURATION`` (``90s``, ``30m``, ``12h``,
    ``7d``, ``2w``) with the journals only they need.

``convert SRC DST``
    Runs ``coopy.convert`` (see :doc:`modern-api`). ``--to-serializer`` and
    ``--to-secret-env`` (or ``--unsigned``) configure the destination; they
    default to the source settings.

Storage options
---------------

Commands that load data accept the settings ``coopy.open`` would need:

``--serializer SPEC``
    ``pickle`` (default), ``json`` (built-in types only), or
    ``module:name`` of a serializer object, class or zero-argument factory,
    for example ``myapp.storage:make_serializer``.

``--secret-env VAR``
    Name of an environment variable holding the HMAC secret (its UTF-8
    bytes). Repeat it for a key list, newest first. Secrets are never passed
    as arguments, so they stay out of shell history and process listings.

``--schemas SPEC`` / ``--state-schemas SPEC``
    ``module:name`` of the ``ActionSchemas`` / ``StateSchemas`` object or
    factory your application passes to ``coopy.open``.

Example::

    export PYTHONPATH=/srv/myapp
    export COOPY_SECRET=...
    python -m coopy inspect data
    python -m coopy verify data --secret-env COOPY_SECRET \
        --state-schemas myapp.storage:state_schemas
    python -m coopy prune data --keep 3 --keep-for 7d
