"""Report test results in the format consumed by Allure 3."""

import hashlib
import json
import mimetypes
import shutil
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Optional

import tmt.log
import tmt.steps
import tmt.steps.report
import tmt.utils
from tmt.container import container, field
from tmt.result import BaseResult, Result, ResultGuestData, ResultOutcome
from tmt.utils import Path

#: Name of the directory the results are written into when no path is given.
DEFAULT_RESULTS_DIRECTORY = 'allure-results'

#: Mapping of tmt results to Allure statuses.
ALLURE_STATUS: dict[ResultOutcome, str] = {
    ResultOutcome.PASS: 'passed',
    ResultOutcome.FAIL: 'failed',
    ResultOutcome.INFO: 'skipped',
    ResultOutcome.SKIP: 'skipped',
    ResultOutcome.ERROR: 'broken',
    ResultOutcome.WARN: 'broken',
    ResultOutcome.PENDING: 'broken',
}


def _timestamp_to_millis(timestamp: str) -> int:
    """
    Convert a tmt timestamp into the number of milliseconds since the epoch.

    tmt stores timestamps with a timezone, a timestamp without one is taken as UTC.
    """

    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise tmt.utils.ReportError(f"Malformed timestamp '{timestamp}'.") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return int(parsed.timestamp() * 1000)


def _duration_to_millis(duration: str) -> int:
    """
    Convert a tmt duration into the number of milliseconds.

    The duration is stored as ``HH:MM:SS``, hours are not limited to two digits.
    """

    parts = duration.split(':')

    if len(parts) != 3:
        raise tmt.utils.ReportError(f"Malformed duration '{duration}'.")

    try:
        hours, minutes, seconds = (int(part) for part in parts)
    except ValueError as exc:
        raise tmt.utils.ReportError(f"Malformed duration '{duration}'.") from exc

    return ((hours * 60 + minutes) * 60 + seconds) * 1000


def result_times(result: BaseResult, now: datetime) -> tuple[int, int]:
    """
    Determine the start and stop of a result in milliseconds.

    tmt records the timestamps it managed to collect, missing pieces are
    derived from the duration. A result without any timing information is
    reported as a point in time.

    :param result: a result to inspect.
    :param now: the moment the report is being written, used as the end of a
        result which knows its duration only.
    """

    start_time = result.start_time
    end_time = result.end_time
    duration = result.duration

    if start_time and end_time:
        start, stop = _timestamp_to_millis(start_time), _timestamp_to_millis(end_time)

        if stop < start:
            raise tmt.utils.ReportError(
                f"Result '{result.name}' ends before it starts, '{start_time}' and '{end_time}'."
            )

        return start, stop

    if end_time and duration:
        stop = _timestamp_to_millis(end_time)

        return stop - _duration_to_millis(duration), stop

    if end_time:
        stop = _timestamp_to_millis(end_time)

        return stop, stop

    if start_time and duration:
        start = _timestamp_to_millis(start_time)

        return start, start + _duration_to_millis(duration)

    if start_time:
        start = _timestamp_to_millis(start_time)

        return start, start

    if duration:
        stop = int(now.timestamp() * 1000)

        return stop - _duration_to_millis(duration), stop

    return 0, 0


def full_name(
    *,
    plan_name: str,
    guest_name: str,
    result_name: str,
    subresult_name: Optional[str] = None,
) -> str:
    """
    Build the Allure ``fullName`` of a result.

    Allure groups results with the same ``fullName`` into a single history
    entry, therefore the name is built from all the parts identifying a test
    run: the plan, the guest and the test itself.
    """

    parts = ['v1', 'sub' if subresult_name else 'main', plan_name, guest_name, result_name]

    if subresult_name is not None:
        parts.append(subresult_name)

    return json.dumps(parts, ensure_ascii=False, separators=(',', ':'))


def _guest_labels(guest: Optional[ResultGuestData]) -> list[dict[str, str]]:
    """
    Turn guest data into Allure labels.
    """

    if guest is None:
        return []

    return [
        {'name': 'guest', 'value': guest.name or ''},
        {'name': 'guest-role', 'value': guest.role or ''},
        {'name': 'guest-address', 'value': guest.primary_address or ''},
    ]


def _inside(path: Path, root: Path) -> Optional[Path]:
    """
    Resolve a log path, refusing anything outside the given directory.

    Logs are reported only when they live under the execute workdir, a path
    pointing elsewhere is not followed.
    """

    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()

    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None

    return candidate


def _failure_log_text(path: Path) -> Optional[str]:
    """
    Read a failure log and join its entries.

    A failure log is a YAML list of strings. Anything which cannot be read or
    parsed is left out, such a log is reported as an attachment instead.
    """

    try:
        content = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None

    try:
        entries = tmt.utils.yaml_to_list(content)
    except tmt.utils.GeneralError:
        return None

    if not all(isinstance(entry, str) for entry in entries):
        return None

    if not any(entry != '' for entry in entries):
        return None

    return '\n'.join(entries)


def _attachment(path: Path, output_directory: Path) -> Optional[dict[str, str]]:
    """
    Copy a log into the results directory and describe it as an Allure attachment.
    """

    target = output_directory / f'{uuid.uuid4()}-attachment{path.suffix or ".txt"}'

    try:
        shutil.copy2(path, target)
    except OSError:
        return None

    return {
        'name': path.name,
        'source': target.name,
        'type': mimetypes.guess_type(path.name)[0] or 'text/plain',
    }


def result_payload(
    result: BaseResult,
    *,
    plan_name: str,
    guest: Optional[ResultGuestData],
    output_directory: Path,
    source_directory: Path,
    now: datetime,
    parent_name: Optional[str] = None,
) -> dict[str, object]:
    """
    Convert a result into an Allure result payload.

    :param result: a result or a subresult to convert.
    :param plan_name: name of the plan the result belongs to.
    :param guest: guest the result was produced on.
    :param output_directory: directory the attachments are copied into.
    :param source_directory: directory the logs are read from, everything
        outside of it is refused.
    :param now: the moment the report is being written.
    :param parent_name: name of the parent result, set for subresults.
    """

    guest_name = guest.name if guest is not None else ''
    start, stop = result_times(result, now)
    full = full_name(
        plan_name=plan_name,
        guest_name=guest_name,
        result_name=parent_name or result.name,
        subresult_name=result.name if parent_name else None,
    )

    payload: dict[str, object] = {
        'uuid': str(uuid.uuid4()),
        'historyId': hashlib.sha256(full.encode('utf-8')).hexdigest(),
        'name': f'{parent_name} :: {result.name}' if parent_name else result.name,
        'fullName': full,
        'status': ALLURE_STATUS[result.result],
        'stage': 'finished',
        'start': start,
        'stop': stop,
        'labels': _guest_labels(guest),
    }

    note = '\n'.join(result.note)
    traces: list[str] = []
    consumed: set[Path] = set()

    for log in result.failure_logs:
        path = _inside(log, source_directory)

        if path is None:
            continue

        text = _failure_log_text(path)

        if text is None:
            continue

        traces.append(text)
        consumed.add(path)

    if note or traces:
        details: dict[str, str] = {}

        if note:
            details['message'] = note

        if traces:
            details['trace'] = '\n\n'.join(traces)

        payload['statusDetails'] = details

    attachments: list[dict[str, str]] = []
    seen: set[Path] = set()

    for log in [*result.log, *result.failure_logs]:
        path = _inside(log, source_directory)

        if path is None or path in consumed or path in seen:
            continue

        seen.add(path)
        copied = _attachment(path, output_directory)

        if copied is not None:
            attachments.append(copied)

    if attachments:
        payload['attachments'] = attachments

    return payload


def write_payload(payload: dict[str, object], output_directory: Path) -> Path:
    """
    Write a payload into the results directory.

    The file is written under a temporary name first and renamed afterwards,
    so a reader never picks up a partially written result.
    """

    target = output_directory / f'{payload["uuid"]}-result.json'
    temporary = output_directory / f'.{payload["uuid"]}.partial'

    temporary.write_text(json.dumps(payload, ensure_ascii=False))
    temporary.rename(target)

    return target


def convert_result(
    result: Result,
    *,
    plan_name: str,
    output_directory: Path,
    source_directory: Path,
    now: datetime,
    warn: Callable[[str], None],
) -> list[Path]:
    """
    Write a result and its subresults into the results directory.

    :param result: a result to convert.
    :param plan_name: name of the plan the result belongs to.
    :param output_directory: directory the results are written into.
    :param source_directory: directory the logs are read from.
    :param now: the moment the report is being written.
    :param warn: a callable used to report problems.
    :returns: paths of the written files.
    """

    written: list[Path] = []

    payload = result_payload(
        result,
        plan_name=plan_name,
        guest=result.guest,
        output_directory=output_directory,
        source_directory=source_directory,
        now=now,
    )
    written.append(write_payload(payload, output_directory))

    for subresult in result.subresult:
        try:
            payload = result_payload(
                subresult,
                plan_name=plan_name,
                guest=result.guest,
                output_directory=output_directory,
                source_directory=source_directory,
                now=now,
                parent_name=result.name,
            )
        except (tmt.utils.ReportError, OSError):
            warn(f"Failed to convert subresult '{subresult.name}' of result '{result.name}'.")
            continue

        written.append(write_payload(payload, output_directory))

    return written


@container
class ReportAllureData(tmt.steps.report.ReportStepData):
    file: Optional[Path] = field(
        default=None,
        option='--file',
        metavar='PATH',
        help='Path to the directory to store Allure results in.',
        normalize=tmt.utils.normalize_path,
    )


@tmt.steps.provides_method('allure')
class ReportAllure(tmt.steps.report.ReportPlugin[ReportAllureData]):
    """
    Save test results in the format consumed by Allure 3.

    Allure 3 no longer reads the JUnit XML format, it builds its report from
    the ``*-result.json`` files found in a results directory. Each tmt result
    becomes one result file, each of its subresults becomes a separate one,
    linked through the parent name.

    When ``file`` is not specified, results are written into a directory named
    ``allure-results`` located in the step workdir.

    .. code-block:: yaml

        # Enable allure report from the command line
        tmt run --all report --how allure
        tmt run --all report --how allure --file /tmp/allure-results

    .. code-block:: yaml

        # Use allure as the default report for given plan
        report:
            how: allure
            file: /tmp/allure-results

    Possible test results and their mapping to Allure statuses:

    * ``pass`` - ``passed``
    * ``fail`` - ``failed``
    * ``skip`` or ``info`` - ``skipped``
    * ``error``, ``warn``, or ``pending`` - ``broken``

    Logs recorded by the test are stored as attachments. A failure log is
    parsed and stored in the ``trace`` field instead, as long as it can be
    read; otherwise it becomes an attachment too.

    This plugin is available since tmt 1.80.
    """

    _data_class = ReportAllureData

    @property
    def _preserved_workdir_members(self) -> set[str]:
        """
        A set of members of the step workdir that should not be removed.
        """

        members = super()._preserved_workdir_members

        if self.data.file is None:
            members = {*members, DEFAULT_RESULTS_DIRECTORY}

        return members

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Read executed tests and write allure results
        """

        super().go(logger=logger)

        if self.is_dry_run:
            return

        output_directory = self.data.file or self.phase_workdir / DEFAULT_RESULTS_DIRECTORY

        try:
            output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise tmt.utils.ReportError(
                f"Failed to create the output directory '{output_directory}'."
            ) from exc

        now = datetime.now().astimezone()

        execute_workdir = self.step.plan.execute.workdir

        if execute_workdir is None:
            raise tmt.utils.ReportError('The execute step has no workdir.')

        source_directory = execute_workdir

        for result in self.step.plan.execute.results():
            try:
                written = convert_result(
                    result,
                    plan_name=self.step.plan.name,
                    output_directory=output_directory,
                    source_directory=source_directory,
                    now=now,
                    warn=self.warn,
                )
            except (tmt.utils.ReportError, OSError) as exc:
                self.warn(f"Failed to convert result '{result.name}': {exc}")
                continue

            self.verbose(
                'result',
                f"Result '{result.name}' written into {len(written)} file(s).",
                color='green',
            )

        self.info('output', output_directory, color='yellow')
