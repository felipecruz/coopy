"""Source checks for direct calls that make replay non-deterministic."""

from __future__ import annotations

import ast
import inspect
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from .error import ConfigurationError, NonDeterministicCallError

logger = logging.getLogger(__name__)

VALIDATION_POLICIES = ("warn", "strict", "off")

FORBIDDEN_OBJECTS = ("datetime", "date")

DATE_FUNCS = ("today",)

DATETIME_FUNCS = ("now", "utcnow")

FORBIDDEN_FUNCS = DATE_FUNCS + DATETIME_FUNCS

ARGUMENT = "pass the value as a method argument"

# Fully qualified call -> what to use instead.
SOURCES = {
    "datetime.datetime.now": "self._clock.now()",
    "datetime.datetime.utcnow": "self._clock.utcnow()",
    "datetime.datetime.today": "self._clock.now()",
    "datetime.date.today": "self._clock.today()",
    "time.time": "self._clock.time()",
    "time.time_ns": "self._clock.time()",
    "time.monotonic": "self._clock.monotonic()",
    "time.monotonic_ns": "self._clock.monotonic()",
    "time.perf_counter": "self._clock.monotonic()",
    "time.perf_counter_ns": "self._clock.monotonic()",
    "random.random": "self._env.random()",
    "random.uniform": "self._env.uniform()",
    "random.randint": "self._env.randint()",
    "random.randrange": "self._env.randint()",
    "random.choice": "self._env.choice()",
    "random.choices": "self._env.choice()",
    "random.shuffle": "self._env.shuffle()",
    "random.sample": "self._env.sample()",
    "random.getrandbits": "self._env.token_bytes()",
    "random.randbytes": "self._env.token_bytes()",
    "uuid.uuid1": "self._env.uuid4()",
    "uuid.uuid4": "self._env.uuid4()",
    "os.urandom": "self._env.token_bytes()",
    "os.getrandom": "self._env.token_bytes()",
    "secrets.token_bytes": "self._env.token_bytes()",
    "secrets.token_hex": "self._env.token_hex()",
    "secrets.token_urlsafe": "self._env.token_urlsafe()",
    "secrets.choice": "self._env.choice()",
    "secrets.randbelow": "self._env.randint()",
    "secrets.randbits": "self._env.token_bytes()",
}

# Every other public call on these modules is flagged too (random.gauss(), ...).
SOURCE_MODULES = ("random", "secrets")

# Seeded generators are deterministic; random.Random() without a seed is not
# detected.
ALLOWED = ("random.Random",)

_MODULE_ALIASES = {"posix": "os", "nt": "os", "_datetime": "datetime"}
_TRACKED = {name.split(".")[0] for name in SOURCES}


@dataclass(frozen=True)
class NonDeterministicCall:
    """A direct call found in method source.

    ``written`` is the call as written (``dt.now``), ``source`` the resolved
    name (``datetime.datetime.now``) and ``line`` its line in ``filename``.
    ``legacy`` marks the ``datetime.now()``/``date.today()`` form that coopy
    rejected before validation policies existed; ``"warn"`` still rejects it.
    """

    written: str
    source: str
    line: int
    replacement: str
    legacy: bool = False
    filename: str | None = None

    def describe(self) -> str:
        where = f"{self.filename}:{self.line}" if self.filename else f"line {self.line}"
        resolved = "" if self.written == self.source else f" ({self.source})"
        hint = self.replacement
        if hint.startswith("self."):
            hint = f"use {hint} instead"
        return f"{self.written}(){resolved} at {where}; {hint}"


def _dotted(node: ast.expr) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return parts[::-1]


def _replacement(source: str) -> str | None:
    if source in ALLOWED:
        return None
    if source in SOURCES:
        return SOURCES[source]
    module, _, name = source.partition(".")
    if module in SOURCE_MODULES and name and "." not in name and not name.startswith("_"):
        return ARGUMENT
    return None


def imports_of(tree: ast.AST) -> dict[str, str]:
    """Map names bound by ``import`` statements anywhere in ``tree`` to their target."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    names[alias.asname] = alias.name
                else:
                    top = alias.name.split(".")[0]
                    names[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                if alias.name != "*":
                    names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names


def _global_name(value: Any) -> str | None:
    if isinstance(value, ModuleType):
        return _MODULE_ALIASES.get(value.__name__, value.__name__)
    module = getattr(value, "__module__", None)
    name = getattr(value, "__name__", None)
    if not isinstance(module, str) or not isinstance(name, str):
        return None
    module = _MODULE_ALIASES.get(module, module)
    if module not in _TRACKED:
        return None
    return f"{module}.{name}"


class NodeVisitor(ast.NodeVisitor):
    """Collect calls that resolve to a non-deterministic source."""

    def __init__(self, imports: dict[str, str] | None = None) -> None:
        self.imports = imports or {}
        self.calls: list[NonDeterministicCall] = []

    def visit_Call(self, node: ast.Call) -> None:
        parts = _dotted(node.func)
        if parts and parts[0] not in ("self", "cls"):
            # self._clock and self._env calls, and any other attribute of the
            # domain, are accepted.
            self._check(node, parts)
        self.generic_visit(node)

    def _check(self, node: ast.Call, parts: list[str]) -> None:
        written = ".".join(parts)
        legacy = len(parts) == 2 and parts[0] in FORBIDDEN_OBJECTS and parts[1] in FORBIDDEN_FUNCS
        base = self.imports.get(parts[0])
        if base is None:
            # Unknown names: treat datetime/date as the datetime classes, as
            # coopy always has, and anything else as written (time.time()).
            base = f"datetime.{parts[0]}" if legacy else parts[0]
        source = ".".join([base, *parts[1:]])
        replacement = _replacement(source)
        if replacement is None and legacy and source.startswith("datetime."):
            # date.now() and datetime.today() were always rejected too.
            replacement = f"self._clock.{parts[1]}()"
        if replacement is not None:
            self.calls.append(
                NonDeterministicCall(written, source, node.lineno, replacement, legacy=legacy)
            )


def find_calls(source: str, imports: dict[str, str] | None = None) -> list[NonDeterministicCall]:
    """Return the non-deterministic calls in ``source``.

    ``imports`` maps names visible to the code (usually the method's module
    imports) to what they refer to; imports inside ``source`` take precedence.
    """
    tree = ast.parse(source)
    visitor = NodeVisitor({**(imports or {}), **imports_of(tree)})
    visitor.visit(tree)
    return visitor.calls


def validate_date_datetime_calls(function: str) -> bool:
    """False when ``function`` calls ``datetime.now()``/``date.today()`` style sources."""
    return not any(call.legacy for call in find_calls(function))


def unindent_source(source_lines: list[str]) -> str:
    source = source_lines[0]
    unindent_level = len(source) - len(source.lstrip())
    return "\n".join([line[unindent_level:] for line in source_lines])


def module_imports(
    function: Callable[..., Any], cache: dict[str, dict[str, str]] | None = None
) -> dict[str, str]:
    """Resolve the names a function's module imports, from its source and globals.

    ``cache`` keeps each module's parsed imports across calls.
    """
    cache = {} if cache is None else cache
    module_name = getattr(function, "__module__", None) or ""
    if module_name not in cache:
        cache[module_name] = {}
        module = sys.modules.get(module_name)
        if module is not None:
            try:
                cache[module_name] = imports_of(ast.parse(inspect.getsource(module)))
            except (OSError, TypeError, SyntaxError):
                pass
    names = dict(cache[module_name])
    for name, value in getattr(function, "__globals__", {}).items():
        resolved = _global_name(value)
        if resolved is not None:
            names[name] = resolved
    return names


def check_policy(policy: str) -> None:
    if policy not in VALIDATION_POLICIES:
        raise ConfigurationError("validation must be 'warn', 'strict' or 'off'")


def validate_system(system_instance: Any, policy: str = "warn") -> bool:
    """Check each method's source for direct non-deterministic calls.

    ``"warn"`` logs a warning for each call but raises
    ``NonDeterministicCallError`` for ``datetime.now()``/``date.today()``
    written that way, as earlier releases did; ``"strict"`` raises for every
    call found; ``"off"`` skips the check. Methods without source are skipped
    with a warning.
    """
    check_policy(policy)
    if policy == "off":
        return True
    cls_name = type(system_instance).__name__
    parsed: dict[str, dict[str, str]] = {}
    for method_name, method in inspect.getmembers(system_instance, predicate=inspect.ismethod):
        if method_name.startswith("__") and method_name.endswith("__"):
            continue
        try:
            source_lines, first_line = inspect.getsourcelines(method)
        except (OSError, TypeError):
            # e.g. classes defined in a REPL or shipped without sources
            logger.warning("Could not validate %s: source code not available" % method_name)
            continue
        fixed_source = unindent_source([line.rstrip("\r\n") for line in source_lines])
        function = inspect.unwrap(method.__func__)
        try:
            filename = inspect.getsourcefile(function)
        except TypeError:
            filename = None
        calls = [
            NonDeterministicCall(
                call.written,
                call.source,
                call.line + max(first_line, 1) - 1,
                call.replacement,
                legacy=call.legacy,
                filename=filename,
            )
            for call in find_calls(fixed_source, module_imports(function, parsed))
        ]
        rejected = calls if policy == "strict" else [call for call in calls if call.legacy]
        for call in calls:
            if call not in rejected:
                logger.warning(
                    "%s.%s calls %s; replay will not reproduce it",
                    cls_name,
                    method_name,
                    call.describe(),
                )
        if rejected:
            raise NonDeterministicCallError(cls_name, method_name, rejected)
    return True
