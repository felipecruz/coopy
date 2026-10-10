"""Explicit storage codecs and action migrations; no automatic format guessing."""

from __future__ import annotations

import base64
import copy
import json
import math
import pickle
from datetime import date, datetime
from io import BytesIO
from typing import Any, BinaryIO, Callable, Mapping, Protocol

from coopy.error import CoopyError
from coopy.foundation import Action, RecordClock


class SerializationError(CoopyError, ValueError):
    """Unknown type, unsupported format/schema, or invalid encoded value."""


class Writer(Protocol):
    def dump(self, value: Any) -> None: ...
    def clear_memo(self) -> None: ...


class Reader(Protocol):
    def load(self) -> Any: ...


class Serializer(Protocol):
    """Each reader/writer owns one stream; loads/dumps own one record."""

    def writer(self, file: BinaryIO) -> Writer: ...
    def reader(self, file: BinaryIO) -> Reader: ...
    def dumps(self, value: Any) -> bytes: ...
    def loads(self, data: bytes) -> Any: ...


class _AliasUnpickler(pickle.Unpickler):
    def __init__(self, file: BinaryIO, aliases: Mapping[tuple[str, str], type[Any]]) -> None:
        super().__init__(file)
        self.aliases = aliases

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) in self.aliases:
            return self.aliases[(module, name)]
        return super().find_class(module, name)


class PickleSerializer:
    """Trusted pickle, with optional aliases for moved/renamed classes."""

    format_name = "pickle"

    def __init__(self, *, class_aliases: Mapping[tuple[str, str], type[Any]] | None = None) -> None:
        self.class_aliases = dict(class_aliases or {})

    def writer(self, file: BinaryIO) -> Writer:
        return pickle.Pickler(file, pickle.HIGHEST_PROTOCOL)

    def reader(self, file: BinaryIO) -> Reader:
        return _AliasUnpickler(file, self.class_aliases)

    def dumps(self, value: Any) -> bytes:
        return pickle.dumps(value, pickle.HIGHEST_PROTOCOL)

    def loads(self, data: bytes) -> Any:
        return self.reader(BytesIO(data)).load()


Encoder = Callable[[Any], Any]
Decoder = Callable[[Any], Any]


class TypeRegistry:
    """Stable wire names mapped to explicit, application-trusted codecs."""

    def __init__(self) -> None:
        self._types: dict[type[Any], tuple[str, Encoder]] = {}
        self._names: dict[str, tuple[type[Any], Decoder]] = {}

    def register(self, name: str, cls: type[Any], *, encode: Encoder, decode: Decoder) -> None:
        if not name or name.startswith("coopy.") or name in self._names or cls in self._types:
            raise SerializationError("Type name/class is reserved or already registered")
        self._types[cls] = (name, encode)
        self._names[name] = (cls, decode)


class _JsonWriter:
    def __init__(self, serializer: JsonSerializer, file: BinaryIO) -> None:
        self.serializer = serializer
        self.file = file

    def dump(self, value: Any) -> None:
        self.file.write(self.serializer.dumps(value))

    def clear_memo(self) -> None:
        pass


class _JsonReader:
    def __init__(self, serializer: JsonSerializer, file: BinaryIO) -> None:
        self.serializer = serializer
        self.file = file

    def load(self) -> Any:
        data = self.file.readline()
        if not data:
            raise EOFError("No JSON record")
        if not data.endswith(b"\n"):
            raise SerializationError("Truncated JSON record")
        return self.serializer.loads(data)


class JsonSerializer:
    """Versioned JSON trees. Never imports classes named by input data."""

    format_name = "json"

    def __init__(self, registry: TypeRegistry | None = None) -> None:
        self.registry = registry if registry is not None else TypeRegistry()

    def writer(self, file: BinaryIO) -> Writer:
        return _JsonWriter(self, file)

    def reader(self, file: BinaryIO) -> Reader:
        return _JsonReader(self, file)

    def dumps(self, value: Any) -> bytes:
        seen: dict[int, Any] = {}

        def encode(value: Any) -> Any:
            cls = type(value)
            if value is None or cls in (bool, int, float, str):
                return value
            if cls is bytes:
                return {"t": "bytes", "v": base64.b64encode(value).decode("ascii")}
            if cls in (datetime, date):
                return {"t": cls.__name__, "v": value.isoformat()}
            if id(value) in seen:
                raise SerializationError(
                    "JSON requires trees: cyclic/shared objects are unsupported"
                )
            seen[id(value)] = value
            if cls in (list, tuple):
                return {"t": cls.__name__, "v": [encode(item) for item in value]}
            if cls is dict:
                return {"t": "dict", "v": [[encode(k), encode(v)] for k, v in value.items()]}
            if cls in (Action, RecordClock):
                name = "coopy.action" if cls is Action else "coopy.clock"
                state = vars(value)
            else:
                entry = self.registry._types.get(cls)
                if entry is None:
                    raise SerializationError(
                        f"Unregistered type: {cls.__module__}.{cls.__qualname__}"
                    )
                name, encoder = entry
                state = encoder(value)
            return {"t": "object", "n": name, "v": encode(state)}

        try:
            return (
                json.dumps(
                    {"format": "coopy-json", "version": 1, "value": encode(value)},
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except SerializationError:
            raise
        except Exception as error:
            raise SerializationError(f"JSON encoding failed: {error}") from error

    def loads(self, data: bytes) -> Any:
        def decode(value: Any) -> Any:
            if type(value) is float and not math.isfinite(value):
                raise SerializationError("Nonfinite JSON number")
            if value is None or type(value) in (bool, int, float, str):
                return value
            if type(value) is not dict or "t" not in value or "v" not in value:
                raise SerializationError("Invalid JSON node")
            tag, state = value["t"], value["v"]
            expected = {"t", "v", "n"} if tag == "object" else {"t", "v"}
            if set(value) != expected:
                raise SerializationError("Invalid JSON node fields")
            if tag == "bytes":
                return base64.b64decode(state, validate=True)
            if tag == "date":
                return date.fromisoformat(state)
            if tag == "datetime":
                return datetime.fromisoformat(state)
            if tag in ("list", "tuple", "dict"):
                if not isinstance(state, list):
                    raise SerializationError("Invalid collection state")
                if tag == "dict":
                    return {decode(k): decode(v) for k, v in state}
                items = [decode(item) for item in state]
                return tuple(items) if tag == "tuple" else items
            if tag == "object":
                name = value["n"]
                if name in ("coopy.action", "coopy.clock"):
                    cls = Action if name == "coopy.action" else RecordClock
                    obj = cls.__new__(cls)
                    obj.__dict__.update(decode(state))
                    return obj
                entry = self.registry._names.get(name)
                if entry is None:
                    raise SerializationError(f"Unregistered type name: {name}")
                registered, decoder = entry
                result = decoder(decode(state))
                if type(result) is not registered:
                    raise SerializationError(f"Decoder returned wrong type for {name}")
                return result
            raise SerializationError(f"Unknown JSON tag: {tag}")

        def invalid_constant(value: str) -> Any:
            raise SerializationError(f"Invalid JSON constant: {value}")

        try:
            document = json.loads(data, parse_constant=invalid_constant)
            if (
                not isinstance(document, dict)
                or set(document) != {"format", "version", "value"}
                or document["format"] != "coopy-json"
                or type(document["version"]) is not int
                or document["version"] != 1
            ):
                raise SerializationError("Unsupported JSON storage format/version")
            return decode(document["value"])
        except SerializationError:
            raise
        except Exception as error:
            raise SerializationError(f"JSON decoding failed: {error}") from error


Upgrade = Callable[[tuple[Any, ...], dict[str, Any]], tuple[tuple[Any, ...], dict[str, Any]]]


class ActionSchemas:
    """Consecutive per-method upgrades; missing legacy versions mean version 1."""

    def __init__(self, versions: Mapping[str, int] | None = None) -> None:
        self.versions = dict(versions or {})
        if any(type(v) is not int or v < 1 for v in self.versions.values()):
            raise SerializationError("Action versions must be positive integers")
        self._upgrades: dict[tuple[str, int], Upgrade] = {}

    def version(self, method: str) -> int:
        return self.versions.get(method, 1)

    def register(self, method: str, from_version: int, upgrade: Upgrade) -> None:
        key = (method, from_version)
        if (
            type(from_version) is not int
            or not 1 <= from_version < self.version(method)
            or key in self._upgrades
        ):
            raise SerializationError(
                "Upgrade must be unique and advance toward the current version"
            )
        self._upgrades[key] = upgrade

    def upgrade(self, action: Action) -> bool:
        version = getattr(action, "schema_version", 1)
        target = self.version(action.action)
        if type(version) is not int or not 1 <= version <= target:
            raise SerializationError(f"Unsupported schema version for {action.action}: {version}")
        changed = version != target
        if changed:
            action.args, action.kwargs = copy.deepcopy((action.args, action.kwargs))
        while version < target:
            callback = self._upgrades.get((action.action, version))
            if callback is None:
                raise SerializationError(f"Missing upcaster for {action.action} version {version}")
            try:
                result = callback(tuple(action.args), dict(action.kwargs))
                if (
                    not isinstance(result, tuple)
                    or len(result) != 2
                    or not isinstance(result[0], tuple)
                    or not isinstance(result[1], dict)
                    or any(not isinstance(key, str) for key in result[1])
                ):
                    raise SerializationError(
                        "Upcaster must return (tuple arguments, dict keyword arguments)"
                    )
                action.args, action.kwargs = result
            except SerializationError:
                raise
            except Exception as error:
                raise SerializationError(
                    f"Upcaster failed for {action.action} version {version}"
                ) from error
            version += 1
        action.schema_version = target
        return changed
