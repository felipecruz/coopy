import sys
import pytest

from coopy.validation import (validate_date_datetime_calls, validate_system,
                              unindent_source, FORBIDDEN_OBJECTS,
                              FORBIDDEN_FUNCS)
from coopy.error import PrevalentError

@pytest.mark.skipif("sys.version_info <= (2,7)")
def test_check_forbidden_calls():
    import itertools

    bad_code_templ = '''
def func():
    a = []
    b = %s.%s()
    '''
    good_code_templ = '''
def func():
    a = []
    b = clock.%s()
    '''

    for pair in itertools.product(FORBIDDEN_OBJECTS, FORBIDDEN_FUNCS):
        bad_code = bad_code_templ % (pair[0], pair[1])
        code = good_code_templ % (pair[1])

        assert not validate_date_datetime_calls(bad_code)
        assert validate_date_datetime_calls(code)

def test_unindent_source():

    code_templ = \
'''def func(self):
    self.func'''

    code_lines = [
        '    def func(self):',
        '        self.func'
    ]

    assert unindent_source(code_lines) == code_templ

def test_validate_system():
    from datetime import datetime

    class BadSystem(object):
        def __init__(self):
            self.data = []

        def bad_method(self):
            now = datetime.now()
            self.data.append(now)

    with pytest.raises(PrevalentError) as error:
        validate_system(BadSystem())

def test_validate_system_method_with_subscript():
    class GoodSystem(object):
        def __init__(self):
            self.data = []

        def ok_method(self):
            temp = []
            temp_el = temp[0]
            element = self.data[0]

        def ok2_method(self):
            return ''.join([])

    assert validate_system(GoodSystem())
