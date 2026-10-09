"""Recovery must never silently step past a damaged or divergent record."""
import pickle
from datetime import datetime
from pathlib import Path

import pytest

from coopy.base import CoopyProxy, init_persistent_system
from coopy.foundation import Action, RecordClock
from coopy.restore import RecoveryError, RecoveryResult


class Ledger:
    def __init__(self):
        self.values = []

    def add(self, value):
        self.values.append(value)

    def fail(self, value):
        self.values.append(value)
        raise ValueError('expected domain failure')


def action(name='add', value='ok', raised=False):
    result = Action(1, name, datetime(2020, 1, 1), (value,), {})
    result.raised = raised
    return result


def fixture(tmp_path, records, tail=b''):
    proxy = init_persistent_system(Ledger, str(tmp_path))
    journal = Path(proxy.publisher.subscribers[0].file.name)
    proxy.close()
    with journal.open('wb') as file:
        pickler = pickle.Pickler(file, protocol=2)
        for record in records:
            pickler.dump(record)
        boundary = file.tell()
        file.write(tail)
    return journal, boundary


def assert_stops(tmp_path, count, kind, journal, offset=None):
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(RecoveryError) as caught:
        init_persistent_system(Ledger, str(tmp_path), recovery='strict')
    report = caught.value.report
    assert not report.complete
    assert report.replayed == count
    assert report.stop.kind == kind
    assert report.stop.position.file == str(journal)
    if offset is not None:
        assert report.stop.position.offset == offset
    result = init_persistent_system(Ledger, str(tmp_path), recovery='salvage')
    assert isinstance(result, RecoveryResult)
    assert not isinstance(result, CoopyProxy)
    assert result.report == report
    assert isinstance(result.system._clock, RecordClock)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    return result


@pytest.mark.parametrize('tail', [b'\x80\x02', pickle.dumps(action(value='lost'))[:-5]])
def test_truncated_record_is_not_clean_eof(tmp_path, tail):
    journal, boundary = fixture(tmp_path, [action()], tail)
    result = assert_stops(tmp_path, 1, 'decode', journal, boundary)
    assert result.system.values == ['ok']
    assert result.report.stop.position.record == 2


def test_corrupt_middle_never_skips_into_later_records_or_files(tmp_path):
    journal, boundary = fixture(tmp_path, [action()], b'!' + pickle.dumps(action(value='later')))
    later = tmp_path / 'transaction_000000000000004.log'
    later.write_bytes(pickle.dumps(action(value='later file')))
    result = assert_stops(tmp_path, 1, 'decode', journal, boundary)
    assert result.system.values == ['ok']


@pytest.mark.parametrize('raised', [False, True, None])
def test_missing_method_is_not_an_expected_exception(tmp_path, raised):
    journal, _ = fixture(tmp_path, [action(), action('removed', raised=raised), action()])
    result = assert_stops(tmp_path, 1, 'method', journal)
    assert result.system.values == ['ok']
    assert result.report.stop.position.action == 'removed'


@pytest.mark.parametrize('name,raised', [('fail', False), ('add', True), ('fail', None)])
def test_outcome_divergence_stops_and_marks_attempted_mutation(tmp_path, name, raised):
    journal, _ = fixture(tmp_path, [action(), action(name, 'attempt', raised), action()])
    result = assert_stops(tmp_path, 1, 'outcome', journal)
    assert result.system.values == ['ok', 'attempt']
    assert result.report.stop.state_may_be_changed


def test_expected_domain_exception_remains_journaled_and_replayable(tmp_path):
    proxy = init_persistent_system(Ledger, str(tmp_path))
    with pytest.raises(ValueError, match='expected domain failure'):
        proxy.fail('failed mutation')
    proxy.add('after')
    proxy.close()
    restored = init_persistent_system(Ledger, str(tmp_path))
    try:
        assert restored.values == ['failed mutation', 'after']
        assert restored.recovery_report.complete
        assert restored.recovery_report.replayed == 2
        assert restored.recovery_report.expected_failures == 1
    finally:
        restored.close()


def test_legacy_actions_reported_and_empty_file_is_clean_eof(tmp_path):
    legacy = action(value='legacy')
    del legacy.raised
    fixture(tmp_path, [legacy, action(value='modern')])
    (tmp_path / 'transaction_000000000000004.log').touch()
    proxy = init_persistent_system(Ledger, str(tmp_path))
    try:
        assert proxy.values == ['legacy', 'modern']
        assert proxy.recovery_report.complete
        assert len(proxy.recovery_report.legacy_actions) == 1
        assert proxy.recovery_report.legacy_actions[0].record == 1
    finally:
        proxy.close()


def test_invalid_checkpoint_is_reported_without_fallback(tmp_path):
    proxy = init_persistent_system(Ledger, str(tmp_path))
    proxy.close()
    checkpoint = next(tmp_path.glob('snapshot_*.dat'))
    checkpoint.write_bytes(b'\x80\x02')
    with pytest.raises(RecoveryError) as caught:
        init_persistent_system(Ledger, str(tmp_path))
    assert caught.value.report.stop.kind == 'checkpoint'
    result = init_persistent_system(Ledger, str(tmp_path), recovery='salvage')
    assert result.system is None
    assert not result.report.complete


def test_salvage_does_not_initialize_missing_storage(tmp_path):
    missing = tmp_path / 'missing'
    result = init_persistent_system(Ledger, str(missing), recovery='salvage')
    assert result.system is None
    assert not result.report.complete
    assert not missing.exists()


def test_invalid_policy_has_no_storage_effect(tmp_path):
    with pytest.raises(ValueError, match='recovery'):
        init_persistent_system(Ledger, str(tmp_path), recovery='best effort')
    assert not list(tmp_path.iterdir())
