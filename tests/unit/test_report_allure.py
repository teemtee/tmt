"""Unit tests for the ``report/allure`` plugin."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, PropertyMock

import pytest

import tmt.utils
from tmt.result import Result, ResultGuestData, ResultOutcome, SubResult
from tmt.steps.report.allure import (
    ALLURE_STATUS,
    DEFAULT_RESULTS_DIRECTORY,
    ReportAllure,
    ReportAllureData,
    convert_result,
    full_name,
    result_payload,
    result_times,
    write_payload,
)
from tmt.utils import Path

NOW = datetime(2026, 10, 22, 1, 0, tzinfo=UTC)


@pytest.fixture
def output_directory(tmppath: Path) -> Path:
    directory = tmppath / 'allure-results'
    directory.mkdir(parents=True, exist_ok=True)

    return directory


@pytest.fixture
def source_directory(tmppath: Path) -> Path:
    directory = tmppath / 'execute'
    directory.mkdir(parents=True, exist_ok=True)

    return directory


@pytest.fixture
def report_fix(tmppath: Path, root_logger):
    # need to provide genuine workdir paths - mock would break os.path.* calls
    step_mock = MagicMock(workdir=tmppath, is_dry_run=False)
    plan_mock = MagicMock()
    name_property = PropertyMock(return_value='plan')

    type(plan_mock).name = name_property
    type(step_mock).plan = plan_mock

    report = ReportAllure(
        logger=root_logger,
        step=step_mock,
        data=ReportAllureData(name='allure', how='allure'),
        workdir=tmppath / 'allure',
    )
    report.info = MagicMock()
    report.warn = MagicMock()

    results = []

    execute_mock = MagicMock()
    type(execute_mock).results = MagicMock(return_value=results)
    type(execute_mock).workdir = PropertyMock(return_value=tmppath)

    type(plan_mock).execute = execute_mock

    return report, results, tmppath


def _write_log(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content)

    return path


@pytest.mark.parametrize(
    ('outcome', 'expected'),
    [
        (ResultOutcome.PASS, 'passed'),
        (ResultOutcome.FAIL, 'failed'),
        (ResultOutcome.INFO, 'skipped'),
        (ResultOutcome.SKIP, 'skipped'),
        (ResultOutcome.ERROR, 'broken'),
        (ResultOutcome.WARN, 'broken'),
        (ResultOutcome.PENDING, 'broken'),
    ],
)
def test_every_outcome_has_an_allure_status(outcome, expected):
    assert ALLURE_STATUS[outcome] == expected
    assert set(ALLURE_STATUS) == set(ResultOutcome)


def test_times_come_from_start_and_end():
    result = Result(
        name='t1',
        start_time=datetime(2026, 10, 22, 1, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 10, 22, 1, 0, 5, tzinfo=UTC),
    )

    assert result_times(result, NOW) == (1792630800000, 1792630805000)


def test_end_and_duration_give_the_start():
    result = Result(
        name='t1',
        end_time=datetime(2026, 10, 22, 1, 0, 5, tzinfo=UTC),
        duration=timedelta(seconds=5),
    )

    assert result_times(result, NOW) == (1792630800000, 1792630805000)


def test_start_and_duration_give_the_end():
    result = Result(
        name='t1',
        start_time=datetime(2026, 10, 22, 1, 0, 0, tzinfo=UTC),
        duration=timedelta(seconds=5),
    )

    assert result_times(result, NOW) == (1792630800000, 1792630805000)


def test_duration_alone_is_measured_against_now():
    result = Result(name='t1', duration=timedelta(seconds=5))

    assert result_times(result, NOW) == (1792630795000, 1792630800000)


def test_single_timestamp_is_a_point_in_time():
    result = Result(name='t1', start_time=datetime(2026, 10, 22, 1, 0, 0, tzinfo=UTC))

    assert result_times(result, NOW) == (1792630800000, 1792630800000)


def test_result_without_timing_starts_at_the_epoch():
    assert result_times(Result(name='t1'), NOW) == (0, 0)


def test_saved_naive_timestamp_is_taken_as_utc():
    result = Result.from_serialized(
        {
            **Result(name='t1').to_serialized(),
            'start-time': '2026-10-22T01:00:00',
            'end-time': '2026-10-22T01:00:05',
        }
    )

    assert result_times(result, NOW) == (1792630800000, 1792630805000)


def test_zero_duration_is_not_missing():
    result = Result(name='t1', duration=timedelta(0))

    assert result_times(result, NOW) == (1792630800000, 1792630800000)


def test_result_ending_before_it_starts_is_reported():
    result = Result(
        name='t1',
        start_time=datetime(2026, 10, 22, 1, 0, 5, tzinfo=UTC),
        end_time=datetime(2026, 10, 22, 1, 0, 0, tzinfo=UTC),
    )

    with pytest.raises(tmt.utils.ReportError, match='ends before it starts'):
        result_times(result, NOW)


def test_long_duration_is_accepted():
    result = Result(name='t1', duration=timedelta(hours=100))

    assert result_times(result, NOW)[1] - result_times(result, NOW)[0] == 360000000


def test_full_name_differs_for_a_subresult():
    main = full_name(plan_name='plan', guest_name='default-0', result_name='t1')
    sub = full_name(
        plan_name='plan', guest_name='default-0', result_name='t1', subresult_name='sub'
    )

    assert main == '["v1","main","plan","default-0","t1"]'
    assert sub == '["v1","sub","plan","default-0","t1","sub"]'
    assert main != sub


def test_full_name_is_stable_for_the_same_test():
    first = full_name(plan_name='plan', guest_name='default-0', result_name='t1')
    second = full_name(plan_name='plan', guest_name='default-0', result_name='t1')

    assert first == second


def test_guest_labels_are_reported():
    guest = ResultGuestData(name='client-1', role='CLIENT', primary_address='192.0.2.1')
    payload = result_payload(
        Result(name='t1', guest=guest),
        plan_name='plan',
        guest=guest,
        output_directory=Path('/tmp'),
        source_directory=Path('/tmp'),
        now=NOW,
    )

    assert payload['labels'] == [
        {'name': 'guest', 'value': 'client-1'},
        {'name': 'guest-role', 'value': 'CLIENT'},
        {'name': 'guest-address', 'value': '192.0.2.1'},
    ]


def test_guest_labels_without_a_value_are_dropped():
    guest = ResultGuestData(name='default-0', role=None, primary_address='')
    payload = result_payload(
        Result(name='t1', guest=guest),
        plan_name='plan',
        guest=guest,
        output_directory=Path('/tmp'),
        source_directory=Path('/tmp'),
        now=NOW,
    )

    assert payload['labels'] == [{'name': 'guest', 'value': 'default-0'}]


def test_missing_guest_has_no_labels():
    payload = result_payload(
        Result(name='t1'),
        plan_name='plan',
        guest=None,
        output_directory=Path('/tmp'),
        source_directory=Path('/tmp'),
        now=NOW,
    )

    assert payload['labels'] == []


def test_note_becomes_the_status_message(output_directory, source_directory):
    payload = result_payload(
        Result(name='t1', note=['first', 'second']),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert payload['statusDetails'] == {'message': 'first\nsecond'}


def test_result_without_details_has_no_status_details(output_directory, source_directory):
    payload = result_payload(
        Result(name='t1'),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert 'statusDetails' not in payload


def test_failure_log_becomes_the_trace(output_directory, source_directory):
    log = _write_log(source_directory, 'failures.yaml', '- line one\n- line two\n')
    payload = result_payload(
        Result(name='t1', result=ResultOutcome.FAIL, log=[log]),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert payload['statusDetails'] == {'trace': 'line one\nline two'}
    # a consumed failure log must not be copied again as an attachment
    assert 'attachments' not in payload


def test_unreadable_failure_log_falls_back_to_an_attachment(output_directory, source_directory):
    log = _write_log(source_directory, 'failures.yaml', '- [not, a, string]\n')
    result = Result(
        name='t1',
        result=ResultOutcome.FAIL,
        log=[log],
    )
    payload = result_payload(
        result,
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert 'statusDetails' not in payload
    assert payload['attachments'][0]['name'] == 'failures.yaml'
    assert (output_directory / payload['attachments'][0]['source']).is_file()


@pytest.mark.parametrize(
    ('outcome', 'content'),
    [
        (ResultOutcome.FAIL, '- ""\n'),
        (ResultOutcome.FAIL, '[]\n'),
        (ResultOutcome.PASS, '[]\n'),
        (ResultOutcome.INFO, ''),
    ],
    ids=['empty-entry', 'empty-list-fail', 'empty-list-pass', 'empty-file-info'],
)
def test_empty_failure_log_is_not_attached(output_directory, source_directory, outcome, content):
    log = _write_log(source_directory, 'failures.yaml', content)
    payload = result_payload(
        Result(name='t1', result=outcome, log=[log]),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert 'statusDetails' not in payload
    assert 'attachments' not in payload
    assert list(output_directory.iterdir()) == []


def test_empty_regular_log_is_still_attached(output_directory, source_directory):
    log = _write_log(source_directory, 'output.txt', '')
    payload = result_payload(
        Result(name='t1', log=[log]),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert len(payload['attachments']) == 1
    assert payload['attachments'][0]['name'] == 'output.txt'


def test_log_outside_the_source_directory_is_refused(output_directory, source_directory, tmppath):
    outside = _write_log(tmppath, 'outside.log', 'secret\n')
    payload = result_payload(
        Result(name='t1', log=[outside]),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert 'attachments' not in payload
    assert not list(output_directory.glob('*-attachment*'))


def test_traversal_to_a_parent_directory_is_refused(output_directory, source_directory, tmppath):
    _write_log(tmppath, 'outside.log', 'secret\n')
    payload = result_payload(
        Result(name='t1', log=[Path('../outside.log')]),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert 'attachments' not in payload


def test_duplicate_logs_are_attached_once(output_directory, source_directory):
    log = _write_log(source_directory, 'output.txt', 'hello\n')
    payload = result_payload(
        Result(name='t1', log=[log, log]),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert len(payload['attachments']) == 1


def test_missing_log_is_skipped(output_directory, source_directory):
    payload = result_payload(
        Result(name='t1', log=[source_directory / 'no-such-file.txt']),
        plan_name='plan',
        guest=ResultGuestData(),
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
    )

    assert 'attachments' not in payload


def test_payload_is_written_under_its_uuid(output_directory):
    written = write_payload({'uuid': 'abc'}, output_directory)

    assert written == output_directory / 'abc-result.json'
    assert json.loads(written.read_text()) == {'uuid': 'abc'}
    # no partial file survives the atomic rename
    assert list(output_directory.glob('*.partial')) == []


def test_subresults_are_written_as_separate_results(output_directory, source_directory):
    result = Result(
        name='parent',
        subresult=[SubResult(name='one'), SubResult(name='two')],
    )
    written = convert_result(
        result,
        plan_name='plan',
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
        warn=lambda message: None,
    )

    payloads = [json.loads(path.read_text()) for path in written]

    assert len(written) == 3
    assert [payload['name'] for payload in payloads] == [
        'parent',
        'parent :: one',
        'parent :: two',
    ]
    assert payloads[1]['fullName'].startswith('["v1","sub"')


def test_subresult_keeps_the_guest_of_its_parent(output_directory, source_directory):
    guest = ResultGuestData(name='client-1')
    result = Result(name='parent', guest=guest, subresult=[SubResult(name='one')])
    written = convert_result(
        result,
        plan_name='plan',
        output_directory=output_directory,
        source_directory=source_directory,
        now=NOW,
        warn=lambda message: None,
    )

    assert json.loads(written[1].read_text())['labels'][0] == {
        'name': 'guest',
        'value': 'client-1',
    }


def test_plugin_writes_into_its_workdir(report_fix):
    report, results, _ = report_fix
    results.append(Result(name='t1'))

    report.go()

    written = list((report.phase_workdir / DEFAULT_RESULTS_DIRECTORY).glob('*-result.json'))

    assert len(written) == 1
    assert json.loads(written[0].read_text())['name'] == 't1'


def test_plugin_writes_into_the_given_directory(report_fix, tmppath):
    report, results, tmppath = report_fix
    target = tmppath / 'custom-results'
    report.data.directory = target
    results.append(Result(name='t1'))

    report.go()

    assert len(list(target.glob('*-result.json'))) == 1


def test_plugin_keeps_the_default_directory_in_the_workdir(report_fix):
    report, _, _ = report_fix

    assert DEFAULT_RESULTS_DIRECTORY in report._preserved_workdir_members


def test_plugin_does_not_keep_a_given_directory(report_fix, tmppath):
    report, _, _ = report_fix
    report.data.directory = tmppath / 'custom-results'

    assert DEFAULT_RESULTS_DIRECTORY not in report._preserved_workdir_members


def test_plugin_skips_a_dry_run(report_fix):
    report, results, _ = report_fix
    report.step.is_dry_run = True
    results.append(Result(name='t1'))

    report.go()

    assert not (report.phase_workdir / DEFAULT_RESULTS_DIRECTORY).exists()


def test_plugin_reports_when_a_result_cannot_be_converted(report_fix, monkeypatch):
    report, results, _ = report_fix
    results.append(
        Result(
            name='t1',
            start_time=datetime(2026, 10, 22, 1, 0, 5, tzinfo=UTC),
            end_time=datetime(2026, 10, 22, 1, 0, 0, tzinfo=UTC),
        )
    )

    report.go()

    assert report.warn.call_count == 1
    assert "Failed to convert result 't1'" in report.warn.call_args[0][0]
