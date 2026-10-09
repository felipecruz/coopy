import logging
from pathlib import Path
from unittest.mock import patch

import pytest

import coopy
from coopy.base import CoopyProxy, PersistenceControl
from coopy.error import ConfigurationError, CoopyError, LifecycleError, ReplicationError

from .test_controls import Collisions


class CustomPath:
    def __init__(self, path):
        self.path = path

    def __fspath__(self):
        return str(self.path)


@pytest.mark.parametrize("path_type", [str, Path, CustomPath])
@pytest.mark.parametrize("exceptional", [False, True])
def test_context_cleanup_and_paths(tmp_path, path_type, exceptional):
    path = path_type(tmp_path / "nested" / "data")
    failure = ValueError("body")
    try:
        with coopy.open(Collisions, path) as system:
            system.close("domain")
            coopy.control(system).start_snapshot_manager(30)
            timer = system.snapshot_timer
            journal = system.publisher.subscribers[0]
            if exceptional:
                raise failure
    except ValueError as error:
        assert exceptional and error is failure
    assert journal.file.closed
    assert not timer.is_alive()
    coopy.control(system).close()
    with pytest.raises(LifecycleError):
        system.close("after close")
    with coopy.control(coopy.open(Collisions(), path)) as restored:
        assert restored.events == ["domain"]


def test_opt_in_logging(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logger = logging.getLogger("coopy")
    handlers, level = list(logger.handlers), logger.level
    with coopy.open(Collisions, tmp_path / "data"):
        pass
    assert not (tmp_path / "coopy.log").exists()
    assert logger.handlers == handlers
    assert logger.level == level
    try:
        coopy.logging_config(tmp_path)
        coopy.logging_config(tmp_path)
        logger.info("explicit file logging")
        assert (tmp_path / "coopy.log").read_text().count("explicit file logging") == 1
    finally:
        for handler in list(logger.handlers):
            if handler not in handlers:
                logger.removeHandler(handler)
                handler.close()
        logger.setLevel(level)


def test_alias_identity_and_errors(tmp_path):
    assert coopy.open is coopy.init_persistent_system
    with pytest.raises(ConfigurationError) as caught:
        coopy.open(None, tmp_path)
    assert isinstance(caught.value, CoopyError)
    with coopy.open(Collisions, tmp_path) as system:
        system.slave = type("Replica", (), {"synchronized": False, "close": lambda self: None})()
        with pytest.raises(ReplicationError):
            system.count()


@pytest.mark.parametrize("handle", [False, True])
def test_deprecated_replication_aliases(handle):
    system = CoopyProxy(Collisions(), [])
    target = coopy.control(system) if handle else system
    cls = PersistenceControl if handle else CoopyProxy
    with patch.object(cls, "start_primary") as primary:
        with pytest.warns(DeprecationWarning, match="v0.9"):
            target.start_master(port=1234)
        assert primary.call_args.args[1] == 1234
    with patch.object(cls, "start_replica") as replica:
        with pytest.warns(DeprecationWarning, match="v0.9"):
            target.start_slave("localhost", 1234)
        assert replica.call_args.args[1:3] == ("localhost", 1234)
    coopy.control(system).close()


def test_cleanup_continues_and_preserves_body_exception():
    closed = []

    class Resource:
        def close(self):
            closed.append(self)
            if len(closed) == 1:
                raise OSError("cleanup")

    system = CoopyProxy(Collisions(), [Resource(), Resource()])
    error = ValueError("body")
    with pytest.raises(ValueError) as caught:
        with system:
            raise error
    assert caught.value is error
    assert len(closed) == 2
