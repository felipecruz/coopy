Generated API reference
=======================

Signatures, overloads, parameter types, return types, and docstrings below are
generated from the installed package on every Sphinx build. See
:doc:`modern-api` for usage and :doc:`development` for validation commands.
``coopy.open`` aliases ``coopy.init_persistent_system``. Domain-specific methods
are supplied by your application; dynamic proxy dispatch cannot list them here.

Persistence and async controls
------------------------------

.. autosummary::
   :toctree: _generated
   :template: api-object.rst

   coopy.open
   coopy.init_persistent_system
   coopy.control
   coopy.convert
   coopy.prune
   coopy.prune.PruneReport
   coopy.logging_config
   coopy.base.PersistenceControl
   coopy.AsyncPersistent
   coopy.snapshot.SnapshotJob

Decorators and recorded clocks
------------------------------

.. autosummary::
   :toctree: _generated
   :template: api-object.rst

   coopy.decorators.readonly
   coopy.decorators.unlocked
   coopy.decorators.abort_exception
   coopy.foundation.RecordClock

Serialization and migrations
----------------------------

.. autosummary::
   :toctree: _generated
   :template: api-object.rst

   coopy.Serializer
   coopy.serialization.Reader
   coopy.serialization.Writer
   coopy.PickleSerializer
   coopy.JsonSerializer
   coopy.TypeRegistry
   coopy.ActionSchemas
   coopy.StateSchemas

Recovery and errors
-------------------

.. autosummary::
   :toctree: _generated
   :template: api-object.rst

   coopy.restore.RecoveryResult
   coopy.restore.RecoveryReport
   coopy.restore.RecoveryIssue
   coopy.restore.RecoveryPosition
   coopy.restore.RecoveryError
   coopy.CoopyError
   coopy.ClockDivergenceError
   coopy.error.ConfigurationError
   coopy.error.PrevalentError
   coopy.error.PersistenceError
   coopy.error.LifecycleError
   coopy.error.LockError
   coopy.error.FormatError
   coopy.error.ReplicationError
   coopy.integrity.IntegrityError
   coopy.SerializationError
