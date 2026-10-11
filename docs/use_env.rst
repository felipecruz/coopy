.. _use_env:

Recorded random numbers, UUIDs and tokens
=========================================

Random numbers, UUIDs and tokens break replay the same way the time does: a
method that calls ``random.randint()`` or ``uuid.uuid4()`` produces different
state when recovery or a replica runs it again. Each method invocation through
the proxy gets a ``self._env`` next to :doc:`self._clock <use_clock>`; the
journal stores every value it returns and replay hands the same values back.

.. literalinclude:: examples/raffle.py
   :language: python
   :pyobject: Raffle

.. list-table:: Environment API
   :header-rows: 1

   * - Method
     - Result
   * - ``self._env.random()``
     - ``float`` in ``[0.0, 1.0)``, like ``random.random()``.
   * - ``self._env.uniform(a, b)``
     - ``float`` between ``a`` and ``b``, like ``random.uniform()``.
   * - ``self._env.randint(a, b)``
     - ``int`` with ``a <= n <= b``, like ``random.randint()``.
   * - ``self._env.choice(seq)``
     - An element of ``seq``, like ``random.choice()``.
   * - ``self._env.shuffle(items)``
     - Shuffles ``items`` in place, like ``random.shuffle()``.
   * - ``self._env.sample(population, k)``
     - ``k`` distinct elements, like ``random.sample()``.
   * - ``self._env.uuid4()``
     - A random ``uuid.UUID``, like ``uuid.uuid4()``.
   * - ``self._env.token_bytes(nbytes=None)``, ``token_hex()``, ``token_urlsafe()``
     - Like the ``secrets`` functions of the same name (32 bytes by default).

Live values come from the operating system's entropy
(``random.SystemRandom``, ``secrets`` and ``uuid``). ``choice``, ``shuffle``
and ``sample`` record positions rather than elements, so replay returns the
domain's own objects, and mutating the chosen object (``choice(players).score
+= 1``) replays correctly. ``self._env`` only exists while a proxied method
runs: it is not available in ``__init__`` and is never stored in snapshots.
Like the clock, each call records into its own context, so concurrent
``@unlocked`` calls keep their values apart (:doc:`method_decorators`).

Replay
------

Values use the same journal record as clock values (``(method, value)``
pairs, on-disk format 2), in call order, with clock and environment calls
interleaved. Replay must make the same calls in the same order; otherwise it
raises ``coopy.ClockDivergenceError``, exactly as for the clock: a different
call, a call after the recorded values ran out, values left unused, or a
recorded value the replayed arguments could not produce (``randint(1, 6)``
finding ``9``, ``choice()`` on a shorter sequence, ``token_hex(8)`` finding a
64-character token). Recovery reports it as a ``clock`` stop and replicas
become unsynchronized. ``uuid4()`` is stored as its string, so JSON storage
works without registering ``uuid.UUID``; a domain that keeps ``UUID`` objects
in its own state still needs a ``TypeRegistry`` entry for JSON snapshots.

Recorded secrets end up in the journal
--------------------------------------

Every value ``self._env`` returns is written to the journal in plain form,
including ``token_bytes()``, ``token_hex()`` and ``token_urlsafe()``. Anyone
who can read the data directory or its backups, or who receives the
replication stream, can read those tokens. Error messages and
``python -m coopy log`` show only their length. Use recorded tokens for
values that are not secret by themselves (public identifiers, invitation codes
paired with other checks) or protect the data directory accordingly. For
passwords, API keys and other long-lived secrets, generate them outside the
domain and store only a hash, or keep them outside coopy altogether.
``secret=`` (signed storage) authenticates the files but does not encrypt
them.

When to pass values as arguments instead
----------------------------------------

``self._env`` suits values the domain itself decides on: dice rolls, shuffles,
sampling, and identifiers generated as part of a state change. Pass a value
as an argument when the caller already has it or must know it before the call
(a request ID, an idempotency key, an ID the client generated), when it comes
from an outside system, when a raw secret must not reach the journal, or when
the value should be visible in the call itself, for example in the CLI
``log`` output and in schema upgrades. Arguments are journaled too, so they
do not keep secrets out of the journal either.

Type hints and tests
--------------------

Annotate the injected environment with the ``coopy.Env`` protocol, as in the
example above. Live calls receive a recording ``coopy.environment.RecordEnv``;
recovery and replicas receive a replaying ``RestoreEnv``. For tests,
``coopy.testing.SeededEnv(seed)`` returns a reproducible sequence of values
and ``install_env(system, env)`` makes ``self._env`` read from it; see
:doc:`util_api`. Source validation accepts ``self._env`` calls and flags
direct ``random.*``, ``uuid.uuid4()``, ``os.urandom()`` and ``secrets.*`` calls
with the ``self._env`` method to use instead; ``validation="strict"`` rejects
them at open time (see :doc:`use_clock`).
