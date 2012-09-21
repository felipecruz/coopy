import sys
import pytest

from coopy.validation import validate_date_datetime_calls

@pytest.mark.skipif("sys.version_info <= (2,7)")
def test_validate_date_now_call():
    bad_code = '''
def func():
    a = []
    b = datetime.now()
    '''
    code = '''
def func():
    a = []
    b = clock.now()
    '''

    assert not validate_date_datetime_calls(bad_code)
    assert validate_date_datetime_calls(code)

@pytest.mark.skipif("sys.version_info <= (2,7)")
def test_validate_date_today_call():
    bad_code = '''
def func():
    a = []
    b = datetime.today()
    '''
    code = '''
def func():
    a = []
    b = clock.today()
    '''

    assert not validate_date_datetime_calls(bad_code)
    assert validate_date_datetime_calls(code)

@pytest.mark.skipif("sys.version_info <= (2,7)")
def test_validate_date_utcnow_call():
    bad_code = '''
def func():
    a = []
    b = datetime.utcnow()
    '''
    code = '''
def func():
    a = []
    b = clock.utcnow()
    '''

    assert not validate_date_datetime_calls(bad_code)
    assert validate_date_datetime_calls(code)
