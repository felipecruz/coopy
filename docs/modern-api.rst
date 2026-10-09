Typed domain objects and persistence controls
============================================

Both ``coopy.init_persistent_system(Todo, directory)`` and
``coopy.init_persistent_system(Todo(), directory)`` retain the domain type for
static checking. Decorators preserve positional and keyword signatures. The
installed package includes ``py.typed``. Salvage returns
``RecoveryResult[Todo]``; its ``system`` can be ``None`` when no checkpoint can
be decoded. It is not a writable persistent system.

Use ``coopy.control(todo).take_snapshot()`` and ``coopy.control(todo).close()``
for persistence operations. Domain methods named ``close``, ``shutdown``, or
``take_snapshot`` take precedence and are journaled normally. Legacy direct
controls remain available at runtime when the domain has no matching name;
use the control handle for typed code. Other proxy implementation attributes
(such as ``obj``, ``lock`` and ``publisher``) remain reserved.

Typing is gradual: decorators, errors and integrity use strict checks; base
requires annotated definitions. Dynamic replay and networking internals are
not yet strictly checked.
