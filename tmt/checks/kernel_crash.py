"""Associate kdump evidence with the test attempt interrupted by a guest reboot."""

import json
import re
import shlex
import uuid
from typing import TYPE_CHECKING, Any, Optional, cast

import tmt.log
import tmt.utils
from tmt.checks import Check, CheckPlugin, provides_check
from tmt.container import container, field
from tmt.guest import TransferOptions
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import Path, ShellScript
from tmt.utils.environment import Environment, EnvVarValue
from tmt.utils.wait import Deadline

if TYPE_CHECKING:
    from tmt.base.core import DependencySimple, Test
    from tmt.guest import Guest
    from tmt.steps.execute import TestInvocation

CHECK_NAME: str = 'kernel-crash'
REPORT_FILENAME: str = 'kernel-crash.json'
MARKER: re.Pattern[str] = re.compile(r'tmt: boot (\S+) invocation (\S+)')
STS_BOOT: re.Pattern[str] = re.compile(r'sts: boot (\S+) running ')
PREFIX: re.Pattern[str] = re.compile(
    r'^\s*(?:<\d+>)?(?:\[\s*\d+\.\d+\]\s*)?(?:\[\s*[CT]\d+\]\s*)?'
)
HEADLINE: re.Pattern[str] = re.compile(
    r'^(?:BUG:|kernel BUG at|Oops\b|Kernel panic\b|Unable to handle kernel\b|'
    r'Internal error:|general protection fault|[a-z ]+: [0-9a-f]+ \[#\d+\])'
)
FUNCTION: re.Pattern[str] = re.compile(
    r'(?:RIP:\s+[0-9a-f]+:|pc\s*:\s*|NIP\s+\[[0-9a-f]+\]\s*|'
    r'Krnl PSW\s*:\s*\S+\s+\S+\s+\()'
    r'(?:\[<[0-9a-f]+>\]\s*)?([A-Za-z_][\w.]*)\+0x'
)


def parse_signature(log: str) -> tuple[Optional[str], Optional[str]]:
    """Extract the first kernel fault and its architecture-specific symbol."""

    signature: Optional[str] = None
    for line in log.splitlines():
        message = PREFIX.sub('', line).rstrip()
        if signature is None:
            if HEADLINE.match(message):
                signature = message
        elif match := FUNCTION.search(message):
            return signature, match[1]
    return signature, None


def match_dump(
    baseline: dict[str, Any], dumps: list[dict[str, Any]], known: set[str]
) -> Optional[dict[str, Any]]:
    """
    Prefer this attempt's marker, excluding accounted-for and other boots' dumps.

    Markerless dumps use guest-clock timestamps, with a 60-second margin.
    Dumps after the baseline take precedence over dumps inside that margin.
    An incomplete baseline requires a matching marker, because absence from
    its inventory cannot establish that a markerless dump is new.
    """

    marked: list[dict[str, Any]] = []
    unnamed: list[dict[str, Any]] = []
    for dump in sorted(dumps, key=lambda dump: dump['timestamp']):
        if dump['path'] in known or dump['timestamp'] < baseline['timestamp'] - 60:
            continue
        log = dump.get('logs', {}).get('vmcore-dmesg.txt', '')
        markers = MARKER.findall(log)
        if markers:
            # The last invocation marker matters: many tests share one boot.
            if markers[-1] == (baseline['boot_id'], baseline['identity']):
                marked.append(dump)
            continue
        boots = set(STS_BOOT.findall(log))
        if boots and baseline['boot_id'] not in boots:
            continue
        if not baseline['inventory_errors']:
            unnamed.append(dump)

    known.update(dump['path'] for dump in dumps)
    unnamed.sort(key=lambda dump: dump['timestamp'] < baseline['timestamp'])
    candidates = marked or unnamed
    return candidates[0] if candidates else None


@container
class KernelCrashCheck(Check):
    """Configuration of crash evidence collection for preconfigured guests."""

    dump_path: Optional[str] = field(
        default=None,
        help='Dump directory override. By default, follow /etc/kdump.conf and /var/crash.',
    )
    download_vmcore: bool = field(
        default=False,
        help='Download the full vmcore in addition to crash logs.',
    )


@container
class CrashState:
    """Runner-owned identity, inventory and reports retained across attempts."""

    baseline: dict[str, Any] = field(default_factory=dict[str, Any])
    known: set[str] = field(default_factory=set[str])
    reports: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


def _inspect(
    invocation: 'TestInvocation', options: dict[str, Any], deadline: Deadline
) -> dict[str, Any]:
    """Run the standalone inspector under both runner and guest timeouts."""

    with deadline:
        if deadline.is_due:
            raise tmt.utils.GeneralError('Kernel crash collection timed out.')
        timeout = max(1, int(deadline.time_left.total_seconds()))

    script = Path(__file__).with_name('_kernel_crash.py').read_text()
    command = ShellScript(
        f'{invocation.guest.facts.sudo_prefix} timeout -k 5 {timeout}'
        f' python3 -c {shlex.quote(script)} {shlex.quote(json.dumps(options))}'
    )
    output = invocation.guest.execute(command, silent=True, timeout=timeout + 5)
    return cast(dict[str, Any], json.loads(output.stdout or ''))


@provides_check(CHECK_NAME)
class KernelCrash(CheckPlugin[KernelCrashCheck]):
    """
    Detect unexpected reboots and collect evidence from preconfigured kdump.

    Before each attempt, record boot ID, guest time, crash-kernel readiness
    and existing dumps on the runner, and write an invocation marker to the
    kernel log. After recovery, a changed boot with a matching new dump
    fails this check. A changed boot without a matching dump, a connection
    interruption with the same boot, or a failed recovery reports ``error``.
    A requested ``tmt-reboot`` is an expected lifecycle event.

    The check saves ``vmcore-dmesg.txt``, ``kexec-dmesg.log``, a summary and
    a structured JSON report. The check name remains ``kernel-crash``;
    fault signatures and function names appear in notes and reports.
    Full vmcore downloads are optional and use the collection time budget.

    .. code-block:: yaml

        check:
          - how: kernel-crash
            result: respect
            download-vmcore: false

    Kdump must already be configured. The guest needs Python 3.9 or later
    and ``timeout``. Local paths, mounted filesystem
    targets and NFS in ``/etc/kdump.conf`` are supported. NFS is inspected
    through temporary, read-only, bounded mounts. SSH and raw targets need
    an externally mounted copy selected with ``dump-path``.

    Recovery never automatically restarts a test command. Restart-aware
    tests must opt in with ``restart-on-exit-code`` and handle their own
    progress, expected crashes and multihost synchronization. A resumed
    test can read ``TMT_KERNEL_CRASH_REPORT``, a JSON object containing
    ``version: 1`` and a ``reports`` list with one entry per attempt.
    Entries include ``classification``, boot IDs, readiness, dump location,
    signature, function and runner-relative artifact paths.

    Checks affect ordinary test outcomes. With ``result: custom``, the
    adapter must explicitly fold crash reports into its parent outcome.
    This check does not identify individual items within a test command.
    """

    _check_class = KernelCrashCheck

    @classmethod
    def essential_requires(
        cls, guest: 'Guest', test: 'Test', logger: tmt.log.Logger
    ) -> list['DependencySimple']:
        from tmt.base.core import DependencySimple

        return [DependencySimple('/usr/bin/python3'), DependencySimple('/usr/bin/timeout')]

    @classmethod
    def before_test(
        cls,
        *,
        check: KernelCrashCheck,
        invocation: 'TestInvocation',
        environment: Optional[Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        state = cast(CrashState, invocation.check_data.setdefault(CHECK_NAME, CrashState()))
        identity = str(uuid.uuid4())
        report_path = invocation.test_data_path / REPORT_FILENAME
        directory = invocation.check_files_path / CHECK_NAME / f'attempt-{len(state.reports) + 1}'
        directory.mkdir(parents=True, exist_ok=True)
        for path in (invocation.check_files_path / CHECK_NAME, report_path):
            if path not in invocation.runner_owned_paths:
                invocation.runner_owned_paths.append(path)
        invocation.environment['TMT_KERNEL_CRASH_REPORT'] = EnvVarValue(report_path)
        report_path.write_text(json.dumps({'version': 1, 'reports': state.reports}, indent=2))

        try:
            snapshot = _inspect(
                invocation,
                {'dump_path': check.dump_path, 'marker': identity},
                Deadline.from_seconds(60),
            )
            state.known.update(dump['path'] for dump in snapshot['dumps'])
            state.baseline = {
                **snapshot,
                'identity': identity,
            }
            (directory / 'baseline.json').write_text(json.dumps(state.baseline, indent=2))
            if state.reports:
                # A requested reboot does not push the workdir. Publish just
                # the adapter report, including when a snapshot lost this file.
                invocation.guest.push(
                    source=report_path,
                    destination=report_path,
                    options=TransferOptions(protect_args=True, timeout=30),
                )
        except (tmt.utils.GeneralError, ValueError) as error:
            state.baseline = {'identity': identity, 'error': str(error)}

        return []

    @classmethod
    def after_recovery(
        cls,
        *,
        check: KernelCrashCheck,
        invocation: 'TestInvocation',
        environment: Optional[Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        state = cast(CrashState, invocation.check_data[CHECK_NAME])
        baseline = state.baseline
        directory = invocation.check_files_path / CHECK_NAME / f'attempt-{len(state.reports) + 1}'
        deadline = invocation.collection_deadline or Deadline.from_seconds(60)
        notes: list[str] = []
        logs: list[Path] = []
        report: dict[str, Any] = {
            'identity': baseline['identity'],
            'attempt': len(state.reports) + 1,
            'test': invocation.test.name,
            'guest': invocation.guest.name,
            'return_code': invocation.return_code,
            'timestamp': baseline.get('timestamp'),
            'boot_before': baseline.get('boot_id'),
            'boot_after': None,
            'kdump_loaded': baseline.get('kdump_loaded', False),
            'dump': None,
            'signature': None,
            'function': None,
        }
        classification = 'none'
        outcome = ResultOutcome.PASS
        try:
            if not invocation.is_guest_healthy:
                raise tmt.utils.GeneralError('Guest did not return during recovery.')
            if 'error' in baseline:
                raise tmt.utils.GeneralError(f'Cannot record crash baseline: {baseline["error"]}')
            current = _inspect(
                invocation,
                {
                    'dump_path': check.dump_path,
                    'since': baseline['timestamp'],
                    'known': sorted(state.known),
                },
                deadline,
            )
            report['boot_after'] = current['boot_id']
            notes.extend(baseline['errors'])
            notes.extend(current['errors'])
            if not baseline['boot_id'] or not current['boot_id']:
                raise tmt.utils.GeneralError('Cannot read guest boot identity.')
            if invocation.reboot.requested or invocation.reboot_performed:
                classification = 'expected-reboot'
                notes.append('Reboot requested by tmt.')
                state.known.update(dump['path'] for dump in current['dumps'])
            elif current['boot_id'] != baseline['boot_id']:
                dump = match_dump(baseline, current['dumps'], state.known)
                if dump is None:
                    classification = 'unexpected-reboot'
                    outcome = ResultOutcome.ERROR
                    notes.append('Guest rebooted unexpectedly; no matching crash dump found.')
                else:
                    classification = CHECK_NAME
                    outcome = ResultOutcome.FAIL
                    report['dump'] = dump['path']
                    notes.append(f'Confirmed kernel crash; dump: {dump["path"]}')
                    markers = MARKER.findall(dump.get('logs', {}).get('vmcore-dmesg.txt', ''))
                    report['attribution'] = 'invocation-marker' if markers else 'timestamp'
                    notes.append(f'Dump attribution: {report["attribution"]}.')
                    for name, content in dump.get('logs', {}).items():
                        path = directory / name
                        path.write_text(content)
                        logs.append(path.relative_to(invocation.step_workdir))
                    signature, function = parse_signature(
                        dump.get('logs', {}).get('vmcore-dmesg.txt', '')
                    )
                    report.update(signature=signature, function=function)
                    notes.extend(value for value in (signature, function) if value)
                    if not dump.get('has_vmcore'):
                        notes.append('Kdump saved no vmcore.')
                    elif check.download_vmcore:
                        try:
                            path = directory / 'vmcore'
                            _inspect(
                                invocation,
                                {
                                    'action': 'vmcore',
                                    'dump_path': check.dump_path,
                                    'path': dump['path'],
                                    'destination': str(path),
                                },
                                deadline,
                            )
                            with deadline:
                                if deadline.is_due:
                                    raise tmt.utils.GeneralError('Vmcore download timed out.')
                                timeout = max(1, int(deadline.time_left.total_seconds()))
                            invocation.guest.pull(
                                source=path,
                                destination=directory,
                                options=TransferOptions(protect_args=True, timeout=timeout),
                            )
                            logs.append(path.relative_to(invocation.step_workdir))
                        except tmt.utils.GeneralError as error:
                            notes.append(f'Cannot download vmcore: {error}')
            elif invocation.return_code == 255:
                classification = 'connection-interruption'
                outcome = ResultOutcome.ERROR
                notes.append('Test session interrupted; guest boot ID is unchanged.')
        except (tmt.utils.GeneralError, ValueError) as error:
            classification = 'recovery-error'
            outcome = ResultOutcome.ERROR
            notes.append(str(error))
            if isinstance(error, tmt.utils.RunError) and error.returncode == 255:
                invocation.guest_recovered = False

        notes.append(f'Crash kernel was {"loaded" if report["kdump_loaded"] else "not loaded"}.')
        report.update(classification=classification, outcome=outcome.value, notes=notes)
        summary = directory / 'summary.txt'
        summary.write_text('\n'.join([classification, *notes]) + '\n')
        logs.append(summary.relative_to(invocation.step_workdir))
        report['logs'] = [str(path) for path in logs]
        state.reports.append(report)
        serialized = json.dumps({'version': 1, 'reports': state.reports}, indent=2)
        (directory / REPORT_FILENAME).write_text(serialized)
        (invocation.test_data_path / REPORT_FILENAME).write_text(serialized)
        logs.append((directory / REPORT_FILENAME).relative_to(invocation.step_workdir))
        return [CheckResult(name=CHECK_NAME, result=outcome, note=notes, log=logs)]
