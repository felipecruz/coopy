import os

import pytest

from coopy.error import PrevalentError
from coopy.validation import (
    FORBIDDEN_FUNCS,
    FORBIDDEN_OBJECTS,
    unindent_source,
    validate_date_datetime_calls,
    validate_system,
)


def test_check_forbidden_calls():
    import itertools

    bad_code_templ = """
def func():
    a = []
    b = %s.%s()
    """
    good_code_templ = """
def func():
    a = []
    b = clock.%s()
    """

    for pair in itertools.product(FORBIDDEN_OBJECTS, FORBIDDEN_FUNCS):
        bad_code = bad_code_templ % (pair[0], pair[1])
        code = good_code_templ % (pair[1])

        assert not validate_date_datetime_calls(bad_code)
        assert validate_date_datetime_calls(code)


def test_unindent_source():
    code_templ = """def func(self):
    self.func"""

    code_lines = ["    def func(self):", "        self.func"]

    assert unindent_source(code_lines) == code_templ


def test_validate_system():
    from datetime import datetime

    class BadSystem(object):
        def __init__(self):
            self.data = []

        def bad_method(self):
            now = datetime.now()
            self.data.append(now)

    with pytest.raises(PrevalentError):
        validate_system(BadSystem())


def test_validate_system_method_with_subscript():
    class GoodSystem(object):
        def __init__(self):
            self.data = []

        def ok_method(self):
            temp = []
            _temp_el = temp[0]
            _element = self.data[0]

        def ok2_method(self):
            os.urandom(16).encode("hex")
            return "".join([])

    assert validate_system(GoodSystem())


def test_validate_system_without_source():
    from coopy.validation import validate_system

    namespace = {}
    exec("class NoSource(object):\n    def method(self):\n        return 1\n", namespace)

    assert validate_system(namespace["NoSource"]())


def test_module_globals_with_raising_getattr_are_ignored():
    """A module global whose __getattr__ raises (e.g. a closed proxy) is skipped."""
    from coopy.validation import module_imports

    class Exploding:
        def __getattr__(self, name):
            raise RuntimeError("must not be touched")

    namespace = {"closed_proxy": Exploding(), "__name__": "validation_globals"}
    exec("import time\ndef method(self):\n    return time.time()\n", namespace)

    names = module_imports(namespace["method"])
    assert "closed_proxy" not in names
    assert names["time"] == "time"
