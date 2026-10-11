"""``python -m coopy``: inspect, verify and maintain data directories."""

from __future__ import annotations

import argparse
import importlib
import os
import pickle
import pickletools
import re
import reprlib
import sys
from collections.abc import Callable, Iterator, Sequence
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import coopy
from coopy import fileutils, manifest
from coopy.convert import _Recovering
from coopy.error import ConfigurationError
from coopy.foundation import Action, RecordClock
from coopy.integrity import HEADER, IDENTITY_FILE, MAGIC, TAG_SIZE, Integrity
from coopy.locking import DirectoryLock
from coopy.restore import recover
from coopy.utils import inject

TRUST_NOTICE = (
    "Trust notice: this command loads stored data. With the default pickle "
    "serializer that unpickles it, which can run arbitrary code, so use it only "
    "on trusted data directories. The modules defining the stored domain classes "
    "must be importable (add them to PYTHONPATH)."
)

_REPR = reprlib.Repr()
_REPR.maxstring = 40
_REPR.maxother = 40
_REPR.maxlist = _REPR.maxtuple = _REPR.maxdict = 6


class CliError(Exception):
    """A user-facing failure; main() prints it and exits with status 1."""


# -- option resolution ------------------------------------------------------


def resolve(spec: str) -> Any:
    """Import ``module:qualname`` (or ``module.name``) and return the object."""
    module_name, separator, qualname = spec.partition(":")
    if not separator:
        module_name, _, qualname = spec.rpartition(".")
    if not module_name or not qualname:
        raise CliError(f"{spec!r} is not 'module:name'")
    try:
        target: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            target = getattr(target, part)
    except (ImportError, AttributeError) as error:
        raise CliError(f"Cannot import {spec!r} (is it on PYTHONPATH?): {error}") from error
    return target


def _instance(spec: str, *required: str) -> Any:
    """An object from ``spec``; classes and factories are called without arguments."""
    target = resolve(spec)
    if isinstance(target, type) or not all(hasattr(target, name) for name in required):
        if not callable(target):
            raise CliError(f"{spec!r} is not a {' / '.join(required)} object or factory")
        target = target()
    return target


def serializer_option(spec: str | None) -> Any:
    if spec is None or spec == "pickle":
        return None
    if spec == "json":
        return coopy.JsonSerializer()
    return _instance(spec, "dumps", "loads", "reader", "writer")


def secret_option(names: list[str] | None) -> Any:
    if not names:
        return None
    keys = []
    for name in names:
        value = os.environ.get(name)
        if not value:
            raise CliError(f"Environment variable {name!r} holding a secret is unset or empty")
        keys.append(value.encode("utf-8"))
    return keys[0] if len(keys) == 1 else keys


def duration(text: str) -> timedelta:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smhdw]?)", text.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"invalid duration {text!r} (use e.g. 90s, 12h, 7d)")
    unit = {"": "seconds", "s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
    return timedelta(**{unit[match.group(2)]: float(match.group(1))})


def positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, not {text!r}")
    return value


def data_directory(path: str) -> Path:
    """An existing coopy directory; checked before the lock file is created in it."""
    directory = Path(path)
    if not directory.is_dir():
        raise CliError(f"{path!r} is not a directory")
    if not (
        (directory / manifest.MANIFEST_FILE).exists()
        or fileutils.list_snapshot_files(directory)
        or fileutils.list_log_files(directory)
    ):
        raise CliError(f"{path!r} is not a coopy data directory")
    return directory


class _Locked:
    """Hold the writer lock while a command reads, so no writer appends meanwhile."""

    def __init__(self, directory: Path) -> None:
        self.lock = DirectoryLock(directory)

    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        self.lock.release()


def _notice() -> None:
    print(TRUST_NOTICE, file=sys.stderr)


# -- record reading ----------------------------------------------------------


def _count_signed(data: bytes) -> int:
    count, offset = 0, 0
    header_size = len(MAGIC) + HEADER.size
    while offset < len(data):
        header = data[offset : offset + header_size]
        if len(header) != header_size or not header.startswith(MAGIC):
            raise ValueError(f"incomplete signed record at offset {offset}")
        (size,) = HEADER.unpack(header[len(MAGIC) :])
        offset += header_size + size + TAG_SIZE
        if offset > len(data):
            raise ValueError("truncated signed record")
        count += 1
    return count


def _count_pickles(data: bytes) -> int:
    # pickletools only parses opcodes; nothing is imported or constructed.
    stream, count = BytesIO(data), 0
    while stream.tell() < len(data):
        try:
            for _ in pickletools.genops(stream):
                pass
        except Exception as error:
            raise ValueError(f"incomplete pickle record at offset {stream.tell()}") from error
        count += 1
    return count


def count_records(path: Path, serializer: str, signed: bool) -> int | None:
    """Journal records counted without decoding; None for undeclared custom codecs."""
    data = path.read_bytes()
    if signed:
        return _count_signed(data)
    if serializer == "json":
        if data and not data.endswith(b"\n"):
            raise ValueError("truncated JSON record")
        return data.count(b"\n")
    if serializer == "pickle":
        return _count_pickles(data)
    return None


def iter_actions(
    path: Path, serializer: Any, integrity: Integrity | None
) -> Iterator[tuple[int, Action]]:
    """Decode a journal's records in order; raises at the first defect."""
    with open(path, "rb") as file:
        data = file.read()
    stream = BytesIO(data)
    reader = None
    if integrity is None:
        reader = pickle.Unpickler(stream) if serializer is None else serializer.reader(stream)
    record = 0
    while stream.tell() < len(data):
        record += 1
        offset = stream.tell()
        try:
            if reader is not None:
                action = reader.load()
            else:
                assert integrity is not None
                payload = integrity.read(stream, str(path))
                action = pickle.loads(payload) if serializer is None else serializer.loads(payload)
        except Exception as error:
            raise CliError(f"{path.name}: record {record} at offset {offset}: {error}") from error
        if not isinstance(action, Action):
            raise CliError(f"{path.name}: record {record} is not a coopy action")
        yield record, action


def summarize(action: Action) -> str:
    parts = [_REPR.repr(arg) for arg in action.args]
    parts += [f"{key}={_REPR.repr(value)}" for key, value in action.kwargs.items()]
    call = f"{action.action}({', '.join(parts)})"
    if len(call) > 120:
        call = call[:117] + "..."
    timestamp = getattr(action, "timestamp", None)
    when = timestamp.isoformat(sep=" ") if isinstance(timestamp, datetime) else "-"
    line = f"{when}  {call}"
    raised = getattr(action, "raised", None)
    if raised is True:
        line += "  [raised]"
    elif raised is None:
        line += "  [legacy: outcome not recorded]"
    results = getattr(action, "results", None) or []
    if results:
        values = ", ".join(
            value.isoformat() if isinstance(value, date) else repr(value) for value in results[:3]
        )
        more = f", +{len(results) - 3} more" if len(results) > 3 else ""
        line += f"  clock=[{values}{more}]"
    return line


# -- commands ----------------------------------------------------------------


def _checkpoint_number(directory: Path) -> int | None:
    last = fileutils.last_snapshot_file(directory)
    return fileutils.get_number(last) if last else None


def cmd_inspect(args: argparse.Namespace) -> int:
    directory = data_directory(args.directory)
    with _Locked(directory):
        stored = manifest.read(directory)
        print(f"directory: {directory.resolve()}")
        if stored is None:
            print("format: 0 (legacy directory without coopy.json)")
            serializer, signed = "pickle", (directory / IDENTITY_FILE).exists()
        else:
            print(f"format: {manifest.MANIFEST_FILE}")
            for key in sorted(stored):
                print(f"  {key}: {stored[key]}")
            serializer, signed = str(stored.get("serializer")), stored.get("signed") is True
        checkpoint = fileutils.last_snapshot_file(directory)
        number = _checkpoint_number(directory)
        print(f"checkpoint: {checkpoint or 'none'}")
        if signed:
            print("records: signed (counted from envelopes, not verified; run verify)")
        print("files:")
        replay = older = 0
        failed = False
        names = sorted(
            (fileutils.list_snapshot_files(directory) or [])
            + (fileutils.list_log_files(directory) or []),
            key=fileutils.get_number,
        )
        for name in names:
            path = directory / name
            size = path.stat().st_size
            detail = ""
            if name == checkpoint:
                detail = "current checkpoint"
            elif fileutils.SNAPSHOT_REGEX.fullmatch(name):
                detail = "older checkpoint"
            else:
                after = number is None or fileutils.get_number(name) > number
                try:
                    count = count_records(path, serializer, signed)
                except ValueError as error:
                    failed = True
                    detail = f"DAMAGED: {error}"
                else:
                    kind = "replayed on open" if after else "before checkpoint"
                    if count is None:
                        detail = f"actions: unknown (custom serializer), {kind}"
                    else:
                        detail = f"actions: {count}, {kind}"
                        if after:
                            replay += count
                        else:
                            older += count
            print(f"  {name}  {size} bytes  {detail}")
        others = sorted(
            entry.name
            for entry in directory.iterdir()
            if not fileutils.FILE_REGEX.fullmatch(entry.name)
        )
        for name in others:
            print(f"  {name}")
        print(f"actions replayed on open: {replay}")
        print(f"actions before the checkpoint: {older}")
    return 1 if failed else 0


def _recovery_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "serializer": serializer_option(args.serializer),
        "secret": secret_option(args.secret_env),
        "schemas": _instance(args.schemas, "upgrade") if args.schemas else None,
        "state_schemas": _instance(args.state_schemas, "upgrade") if args.state_schemas else None,
    }


def cmd_verify(args: argparse.Namespace) -> int:
    directory = data_directory(args.directory)
    _notice()
    options = _recovery_options(args)
    root: Any = _Recovering()
    inject(root, "_clock", RecordClock())
    with _Locked(directory):
        report = recover(root, directory, mode="strict", **options).report
    print(f"checkpoint: {report.checkpoint}")
    print(f"actions replayed: {report.replayed}")
    print(f"expected failures replayed: {report.expected_failures}")
    if report.legacy_actions:
        print(f"legacy actions without recorded outcome: {len(report.legacy_actions)}")
    print("OK: strict recovery succeeded")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    directory = data_directory(args.directory)
    _notice()
    serializer = serializer_option(args.serializer)
    secret = secret_option(args.secret_env)
    with _Locked(directory):
        manifest.check(directory, serializer=serializer, secret=secret)
        integrity = Integrity.open(directory, secret) if secret is not None else None
        checkpoint = fileutils.last_snapshot_file(directory)
        number = _checkpoint_number(directory)
        for name in fileutils.list_log_files(directory) or []:
            after = number is None or fileutils.get_number(name) > number
            if args.after_checkpoint and not after:
                continue
            where = f"after {checkpoint}" if after else "before the checkpoint"
            print(f"== {name} ({where})")
            for record, action in iter_actions(directory / name, serializer, integrity):
                print(f"{record:6d}  {summarize(action)}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    directory = data_directory(args.directory)
    if not fileutils.list_snapshot_files(directory):
        raise CliError(f"{args.directory!r} has no checkpoint to restore")
    _notice()
    cls = resolve(args.cls)
    if not isinstance(cls, type):
        raise CliError(f"{args.cls!r} is not a class")
    options = _recovery_options(args)
    system = coopy.open(cls, directory, snapshot_compression=args.compression, **options)
    control = coopy.control(system)
    with control:
        replayed = control.recovery_report.replayed
        control.take_snapshot()
    print(f"replayed {replayed} actions; new checkpoint: {fileutils.last_snapshot_file(directory)}")
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    directory = data_directory(args.directory)
    report = coopy.prune(directory, keep=args.keep, keep_for=args.keep_for)
    for name in report.removed:
        print(f"removed {name}")
    print(
        f"removed {len(report.snapshots)} checkpoints and {len(report.journals)} journals; "
        f"kept {len(report.kept_snapshots)} checkpoints"
    )
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    source = data_directory(args.source)
    _notice()
    options = _recovery_options(args)
    target: dict[str, Any] = {}
    if args.to_serializer is not None:
        target["new_serializer"] = serializer_option(args.to_serializer)
    if args.unsigned:
        target["new_secret"] = None
    elif args.to_secret_env:
        target["new_secret"] = secret_option(args.to_secret_env)
    report = coopy.convert(
        source, args.destination, snapshot_compression=args.compression, **options, **target
    )
    print(f"converted {source} -> {args.destination}")
    print(f"source checkpoint: {report.checkpoint}; actions replayed: {report.replayed}")
    return 0


# -- parser ------------------------------------------------------------------


def _loading(parser: argparse.ArgumentParser, *, schemas: bool = True) -> None:
    parser.add_argument(
        "--serializer",
        metavar="SPEC",
        help="'pickle' (default), 'json', or module:name of a serializer object or factory",
    )
    parser.add_argument(
        "--secret-env",
        metavar="VAR",
        action="append",
        help="environment variable holding the HMAC secret; repeat for keys, newest first",
    )
    if schemas:
        parser.add_argument(
            "--schemas", metavar="SPEC", help="module:name of ActionSchemas (or factory)"
        )
        parser.add_argument(
            "--state-schemas", metavar="SPEC", help="module:name of StateSchemas (or factory)"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m coopy",
        description="Inspect, verify and maintain coopy data directories. Every command "
        "holds the directory's writer lock, so it fails while a system has it open.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    loading = f"{TRUST_NOTICE} Secrets are read from environment variables, never arguments."

    inspect = commands.add_parser(
        "inspect",
        help="show files, checkpoint, action counts and format manifest (decodes nothing)",
        description="Show files, the current checkpoint, journal action counts and the "
        "format manifest. Records are counted without unpickling.",
    )
    inspect.add_argument("directory", metavar="DIR")
    inspect.set_defaults(run=cmd_inspect)

    verify = commands.add_parser(
        "verify", help="run strict recovery without writing", description=loading
    )
    verify.add_argument("directory", metavar="DIR")
    _loading(verify)
    verify.set_defaults(run=cmd_verify)

    log = commands.add_parser("log", help="list journaled actions", description=loading)
    log.add_argument("directory", metavar="DIR")
    log.add_argument(
        "--after-checkpoint",
        action="store_true",
        help="only list the actions replayed on open",
    )
    _loading(log, schemas=False)
    log.set_defaults(run=cmd_log)

    snapshot = commands.add_parser(
        "snapshot", help="open DIR as CLASS and write a new checkpoint", description=loading
    )
    snapshot.add_argument("directory", metavar="DIR")
    snapshot.add_argument("cls", metavar="CLASS", help="module:QualName of the root class")
    snapshot.add_argument("--compression", choices=["zstd", "lz4"])
    _loading(snapshot)
    snapshot.set_defaults(run=cmd_snapshot)

    prune = commands.add_parser(
        "prune",
        help="delete old checkpoints and the journals only they need",
        description="Delete checkpoints older than the newest N (and outside --keep-for) "
        "with the journals only they need. Decodes nothing.",
    )
    prune.add_argument("directory", metavar="DIR")
    prune.add_argument("--keep", type=positive, required=True, metavar="N")
    prune.add_argument(
        "--keep-for", type=duration, metavar="DURATION", help="also keep newer ones, e.g. 7d"
    )
    prune.set_defaults(run=cmd_prune)

    convert = commands.add_parser(
        "convert",
        help="copy SRC into a new DST with other storage settings",
        description=loading,
    )
    convert.add_argument("source", metavar="SRC")
    convert.add_argument("destination", metavar="DST")
    _loading(convert)
    convert.add_argument("--to-serializer", metavar="SPEC", help="target serializer")
    target = convert.add_mutually_exclusive_group()
    target.add_argument(
        "--to-secret-env", metavar="VAR", action="append", help="target secret variable"
    )
    target.add_argument("--unsigned", action="store_true", help="write unsigned storage")
    convert.add_argument("--compression", choices=["zstd", "lz4"])
    convert.set_defaults(run=cmd_convert)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run: Callable[[argparse.Namespace], int] = args.run
    try:
        return run(args)
    except (CliError, ConfigurationError) as error:
        print(f"coopy: error: {error}", file=sys.stderr)
    except Exception as error:
        print(f"coopy: error: {type(error).__name__}: {error}", file=sys.stderr)
    return 1
