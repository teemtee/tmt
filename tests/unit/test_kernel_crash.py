"""Crash attribution and collection without causing real kernel panics."""

import json
import os
import subprocess
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

import tmt.checks.kernel_crash as crash
from tmt.base.core import Test as TmtTest
from tmt.checks import CheckEvent, CheckResultInterpret, normalize_test_check
from tmt.checks import _kernel_crash as inspector
from tmt.guest import Guest, GuestSsh, SSHMasterProcessFailedToStartError
from tmt.log import Logger
from tmt.result import Result, ResultInterpret, ResultOutcome
from tmt.steps import Plugin
from tmt.steps.context.abort import AbortStep
from tmt.steps.execute import TestInvocation as TmtInvocation
from tmt.steps.execute.internal import ExecuteInternal, ExecuteInternalData
from tmt.utils import (
    Command,
    CommandOutput,
    GeneralError,
    Path,
    ProcessExitCodes,
    RestartMaxAttemptsError,
)
from tmt.utils.environment import Environment
from tmt.utils.wait import Deadline, Waiting

PANIC: str = '[ 10.0] Kernel panic - not syncing: sysrq triggered crash\n'
FAULT: str = '[ 10.0] BUG: unable to handle page fault\n[ 10.1] RIP: 0010:example_fault+0x1/0x2\n'


class Invocation(TmtInvocation):
    """Invocation with an isolated environment and no surrounding run."""

    @property
    def environment(self) -> Environment:
        assert self._environment is not None
        return self._environment


@pytest.fixture
def invocation(tmppath: Path, root_logger: Logger) -> Invocation:
    phase = MagicMock()
    phase.step_workdir = tmppath
    guest = MagicMock(spec=Guest)
    guest.safe_name = guest.name = 'guest'
    guest.role = None
    guest.become = False
    guest.primary_address = '192.0.2.1'
    guest.topology_address = '192.0.2.1'
    guest.facts.sudo_prefix = ''
    test = TmtTest.from_dict(name='/test', mapping={'test': 'true'}, logger=root_logger)
    test.check = [crash.KernelCrashCheck(how=crash.CHECK_NAME)]
    return Invocation(
        phase=phase, guest=guest, test=test, logger=root_logger, _environment=Environment()
    )


def snapshot(boot: str = 'before', dumps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        'boot_id': boot,
        'timestamp': 1000,
        'kdump_loaded': True,
        'dumps': dumps or [],
        'errors': [],
        'inventory_errors': [],
    }


def dump(
    path: str = '/var/crash/new', timestamp: float = 1010, log: str = FAULT
) -> dict[str, Any]:
    return {
        'path': path,
        'timestamp': timestamp,
        'has_vmcore': True,
        'logs': {'vmcore-dmesg.txt': log, 'kexec-dmesg.log': 'kexec log'},
    }


@pytest.mark.parametrize(
    ('log', 'function'),
    [
        (FAULT, 'example_fault'),
        (PANIC, None),
        ('[ 1.0][ T42] Oops: test\n[ 1.1] pc : example_arm+0x1/0x2', 'example_arm'),
        ('<4>BUG: test\nNIP [c000000000123456] example_ppc+0x1/0x2', 'example_ppc'),
        ('BUG: test\nKrnl PSW : 0704 000003ff (example_s390+0x1/0x2)', 'example_s390'),
        ('divide error: 0000 [#1] SMP', None),
    ],
)
def test_signature(log: str, function: str | None) -> None:
    headline, parsed = crash.parse_signature(log)
    assert headline is not None
    assert parsed == function


def test_warning_and_item_name_do_not_supply_signature() -> None:
    log = 'WARNING: CPU 1\nRIP: 0010:unrelated+0x1/0x2\ntmt: invocation BUG: Oops\n'
    assert crash.parse_signature(log) == (None, None)
    assert crash.parse_signature(log + FAULT)[1] == 'example_fault'


@pytest.mark.parametrize(
    ('candidates', 'expected'),
    [
        ([dump(timestamp=800)], None),
        ([dump(log='tmt: boot old invocation old\n' + FAULT)], None),
        ([dump(log='tmt: boot before invocation previous\n' + FAULT)], None),
        ([dump(log='sts: boot old running test\n' + FAULT)], None),
        ([dump(timestamp=970)], '/var/crash/new'),
        ([dump('/margin', 970), dump('/own', 1010)], '/own'),
        ([dump('/first', 1010), dump('/second', 1020)], '/first'),
        (
            [
                dump('/unnamed', 1001),
                dump('/marked', 1010, 'tmt: boot before invocation own\n' + FAULT),
            ],
            '/marked',
        ),
        ([dump(log='tmt: boot before invocation own\ntmt: boot before invocation later\n')], None),
    ],
)
def test_dump_attribution(candidates: list[dict[str, Any]], expected: str | None) -> None:
    baseline = {**snapshot(), 'identity': 'own'}
    known: set[str] = set()
    selected = crash.match_dump(baseline, candidates, known)
    assert (selected['path'] if selected else None) == expected
    assert known == {candidate['path'] for candidate in candidates}


def test_snapshot_rollback_does_not_reuse_known_dump() -> None:
    baseline = {**snapshot(), 'identity': 'own'}
    candidate = dump(log='tmt: boot before invocation own\n' + FAULT)
    known: set[str] = set()
    assert crash.match_dump(baseline, [candidate], known) is not None
    assert crash.match_dump(baseline, [candidate], known) is None


def test_inaccessible_baseline_requires_marker() -> None:
    baseline = {**snapshot(), 'identity': 'own', 'inventory_errors': ['NFS unavailable']}
    assert crash.match_dump(baseline, [dump()], set()) is None
    assert (
        crash.match_dump(baseline, [dump(log='tmt: boot before invocation own\n' + FAULT)], set())
        is not None
    )


@pytest.mark.parametrize(
    ('boot', 'dumps', 'return_code', 'requested', 'healthy', 'classification', 'outcome'),
    [
        ('after', [dump()], 255, False, True, 'kernel-crash', ResultOutcome.FAIL),
        ('after', [], 255, False, True, 'unexpected-reboot', ResultOutcome.ERROR),
        ('before', [], 255, False, True, 'connection-interruption', ResultOutcome.ERROR),
        ('after', [dump()], 255, True, True, 'expected-reboot', ResultOutcome.PASS),
        ('before', [], 0, True, True, 'expected-reboot', ResultOutcome.PASS),
        ('before', [], 0, False, True, 'none', ResultOutcome.PASS),
        ('after', [], 255, False, False, 'recovery-error', ResultOutcome.ERROR),
    ],
)
def test_classification_and_adapter_report(
    invocation: Invocation,
    monkeypatch: pytest.MonkeyPatch,
    boot: str,
    dumps: list[dict[str, Any]],
    return_code: int,
    requested: bool,
    healthy: bool,
    classification: str,
    outcome: ResultOutcome,
) -> None:
    inspect = MagicMock(side_effect=[snapshot(), snapshot(boot, dumps)])
    monkeypatch.setattr(crash, '_inspect', inspect)
    invocation.invoke_checks_before_test()
    invocation.return_code = return_code
    invocation.guest_recovered = healthy
    if requested:
        invocation.reboot.request_path.write_text('{}')
    results = invocation.invoke_checks_after_recovery()
    assert len(results) == 1
    assert results[0].name == 'kernel-crash'
    assert results[0].result == outcome
    assert results[0].event == CheckEvent.AFTER_RECOVERY
    report = json.loads((invocation.test_data_path / crash.REPORT_FILENAME).read_text())
    assert report['version'] == 1
    record = report['reports'][0]
    assert record['classification'] == classification
    assert record['kdump_loaded'] is True
    if classification == 'kernel-crash':
        assert record['function'] == 'example_fault'
        assert record['dump'] == '/var/crash/new'
        assert any(
            (invocation.step_workdir / path).name == 'vmcore-dmesg.txt' for path in record['logs']
        )
    for path in results[0].log:
        assert (invocation.step_workdir / path).exists()
    if not healthy:
        assert inspect.call_count == 1


def test_reports_and_logs_survive_attempts(
    invocation: Invocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        crash,
        '_inspect',
        MagicMock(
            side_effect=[
                snapshot(),
                snapshot('after', [dump()]),
                snapshot('after'),
                snapshot('later', [dump('/second')]),
            ]
        ),
    )
    for _ in range(2):
        invocation.invoke_checks_before_test()
        invocation.check_results += invocation.invoke_checks_after_recovery()
    assert len(invocation.check_results) == 2
    assert len({str(path) for result in invocation.check_results for path in result.log}) == 8
    report = json.loads((invocation.test_data_path / crash.REPORT_FILENAME).read_text())
    assert len(report['reports']) == 2
    assert report['reports'][0]['identity'] != report['reports'][1]['identity']
    result = Result(name='/test', result=ResultOutcome.PASS, check=invocation.check_results)
    result.interpret_result(
        ResultInterpret.RESPECT, {'kernel-crash': CheckResultInterpret.RESPECT}
    )
    assert result.result == ResultOutcome.FAIL


def test_vmcore_is_opt_in(invocation: Invocation, monkeypatch: pytest.MonkeyPatch) -> None:
    inspect = MagicMock(side_effect=[snapshot(), snapshot('after', [dump()])])
    monkeypatch.setattr(crash, '_inspect', inspect)
    invocation.invoke_checks_before_test()
    invocation.invoke_checks_after_recovery()
    assert inspect.call_count == 2
    invocation.guest.pull.assert_not_called()


def test_vmcore_transfer_error_retains_confirmed_crash(
    invocation: Invocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = invocation.test.check[0]
    assert isinstance(check, crash.KernelCrashCheck)
    check.download_vmcore = True
    monkeypatch.setattr(
        crash, '_inspect', MagicMock(side_effect=[snapshot(), snapshot('after', [dump()]), {}])
    )
    invocation.guest.pull.side_effect = GeneralError('Transfer failed')
    invocation.invoke_checks_before_test()
    result = invocation.invoke_checks_after_recovery()[0]
    assert result.result == ResultOutcome.FAIL
    assert any('Cannot download vmcore' in note for note in result.note)
    assert invocation.guest.pull.call_args.kwargs['options'].timeout <= 60


def test_guest_states_are_isolated(
    invocation: Invocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer_guest = MagicMock(spec=Guest)
    peer_guest.safe_name = peer_guest.name = 'peer'
    peer = Invocation(
        phase=invocation.phase,
        guest=peer_guest,
        test=invocation.test,
        logger=invocation.logger,
        _environment=Environment(),
    )
    monkeypatch.setattr(
        crash,
        '_inspect',
        MagicMock(
            side_effect=[
                snapshot(),
                snapshot(),
                snapshot('after', [dump()]),
                snapshot(),
            ]
        ),
    )
    invocation.invoke_checks_before_test()
    peer.invoke_checks_before_test()
    assert invocation.invoke_checks_after_recovery()[0].result == ResultOutcome.FAIL
    assert peer.invoke_checks_after_recovery()[0].result == ResultOutcome.PASS
    assert invocation.check_data is not peer.check_data
    assert invocation.path != peer.path
    peer_report = json.loads((peer.test_data_path / crash.REPORT_FILENAME).read_text())
    assert peer_report['reports'][0]['guest'] == 'peer'
    assert peer_report['reports'][0]['classification'] == 'none'


def test_expired_collection_still_writes_report(
    invocation: Invocation, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(crash, '_inspect', MagicMock(return_value=snapshot()))
    invocation.invoke_checks_before_test()
    monkeypatch.undo()
    invocation.collection_deadline = Deadline.from_seconds(0)
    result = invocation.invoke_checks_after_recovery()[0]
    assert result.result == ResultOutcome.ERROR
    assert 'timed out' in ' '.join(result.note)
    assert (invocation.test_data_path / crash.REPORT_FILENAME).is_file()


@pytest.fixture
def crash_root(tmppath: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmppath / 'crashes'
    root.mkdir()
    for name, value in [
        ('BOOT_ID', 'boot'),
        ('CRASH_LOADED', '1'),
        ('KDUMP_CONFIG', f'path {root}'),
    ]:
        path = tmppath / name
        path.write_text(value)
        monkeypatch.setattr(inspector, name, path)
    monkeypatch.setattr(inspector, 'KMSG', tmppath / 'kmsg')
    return root


def test_guest_inspector_uses_mtime_and_collects_logs(crash_root: Path) -> None:
    directory = crash_root / 'host-2026-11-04-10:00:00'
    directory.mkdir()
    (directory / 'vmcore-dmesg.txt').write_text(FAULT)
    (directory / 'kexec-dmesg.log').write_text('kexec')
    (directory / 'vmcore').touch()
    os.utime(directory, (1000, 1000))
    baseline = inspector.inspect({'marker': 'own'})
    assert baseline['boot_id'] == 'boot'
    assert baseline['kdump_loaded'] is True
    assert baseline['dumps'] == [{'path': str(directory), 'timestamp': 1000}]
    assert inspector.KMSG.read_text() == '<5>tmt: boot boot invocation own\n'
    evidence = inspector.inspect({'since': 1010})
    assert evidence['dumps'][0]['logs']['vmcore-dmesg.txt'] == FAULT
    assert evidence['dumps'][0]['has_vmcore'] is True
    assert inspector.inspect({'since': 1200})['dumps'] == []
    assert inspector.inspect({'since': 1000, 'known': [str(directory)]})['dumps'] == []


def test_failed_nfs_retains_local_fallback(
    crash_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspector.KDUMP_CONFIG.write_text(
        f'nfs unavailable:/export\npath {crash_root}\nfailure_action dump_to_rootfs\n'
    )
    run = MagicMock(side_effect=subprocess.TimeoutExpired('mount', 20))
    monkeypatch.setattr(inspector, '_run', run)
    errors: list[str] = []
    with inspector.dump_roots(None, errors) as roots:
        assert roots == [(crash_root, str(crash_root))]
    assert errors
    assert 'ro,soft,timeo=50,retrans=2,retry=0' in run.call_args.args


def test_temporary_nfs_mount_is_released_on_collection_error(
    crash_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspector.KDUMP_CONFIG.write_text('nfs server:/export\npath /dumps\n')
    run = MagicMock(side_effect=[subprocess.CalledProcessError(1, 'findmnt'), '', ''])
    monkeypatch.setattr(inspector, '_run', run)
    errors: list[str] = []
    mountpoints: list[Path] = []

    def fail_collection() -> None:
        with inspector.dump_roots(None, errors) as roots:
            root, location = roots[0]
            assert location == 'server:/export/dumps'
            mountpoints.append(Path(root.parent))
            assert root.parent.exists()
            raise RuntimeError('collection failed')

    with pytest.raises(RuntimeError, match='collection failed'):
        fail_collection()
    mountpoint = mountpoints[0]
    assert not mountpoint.exists()
    assert run.call_args.args == ('umount', str(mountpoint))


def test_empty_timestamp_directory_is_not_a_dump(crash_root: Path) -> None:
    (crash_root / 'host-2026-11-04-10:00:00').mkdir()
    assert inspector.inspect({'since': 0})['dumps'] == []


def test_vmcore_staging_is_private(
    crash_root: Path, tmppath: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = crash_root / 'host-2026-11-04-10:00:00'
    directory.mkdir()
    (directory / 'vmcore').write_bytes(b'vmcore contents')
    destination = tmppath / 'stage' / 'vmcore'
    monkeypatch.delenv('SUDO_UID', raising=False)
    inspector.copy_vmcore(
        {
            'dump_path': str(crash_root),
            'path': str(directory),
            'destination': str(destination),
        }
    )
    assert destination.read_bytes() == b'vmcore contents'
    assert destination.stat().st_mode & 0o777 == 0o600


def test_reconnect_probes_have_a_timeout(root_logger: Logger) -> None:
    guest = MagicMock(spec=Guest)
    guest._logger = root_logger
    assert Guest.reconnect(guest, Waiting(deadline=Deadline.from_seconds(10)))
    guest.execute.assert_called_once()
    assert 0 < guest.execute.call_args.kwargs['timeout'] <= 10


def test_ssh_master_respects_collection_deadline(root_logger: Logger) -> None:
    guest = MagicMock(spec=GuestSsh)
    guest._logger = root_logger
    guest.is_ssh_multiplexing_enabled = True
    guest._ssh_master_process_lock = threading.RLock()
    guest._ssh_master_process = MagicMock()
    guest._ssh_master_process.poll.return_value = None
    guest._base_ssh_command = Command('ssh')
    with pytest.raises(SSHMasterProcessFailedToStartError):
        GuestSsh._assert_ssh_master_process(guest, Waiting(deadline=Deadline.from_seconds(0)))
    guest._run_guest_command.assert_not_called()


def test_metadata(root_logger: Logger) -> None:
    check = normalize_test_check(
        'check',
        {
            'how': 'kernel-crash',
            'dump-path': '/mounted/crashes',
            'download-vmcore': True,
        },
        root_logger,
    )
    assert isinstance(check, crash.KernelCrashCheck)
    assert check.dump_path == '/mounted/crashes'
    assert check.download_vmcore is True
    assert check.to_spec()['how'] == 'kernel-crash'


@pytest.fixture
def executor(invocation: Invocation, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Use real execution and recovery control flow with simulated transport."""

    executor = MagicMock(spec=ExecuteInternal)
    executor.data = ExecuteInternalData(name='default', how='tmt')
    executor.discover = MagicMock(step_workdir=invocation.step_workdir)
    executor.step = invocation.phase.step
    executor.step.plan.data_directory = invocation.step_workdir / 'plan-data'
    executor.step.plan.data_directory.mkdir()
    executor.step.plan.provision.ready_guests = [invocation.guest]
    executor._results = []
    executor._login_after_test = None
    executor.verbosity_level = 0
    executor.prepare_tests.return_value = [invocation]
    executor.results.side_effect = lambda: executor._results
    executor._recover.side_effect = lambda inv, log: ExecuteInternal._recover(executor, inv, log)
    executor._can_resume.side_effect = lambda inv: ExecuteInternal._can_resume(executor, inv)
    executor._post_action_pull.side_effect = lambda **kwargs: Plugin._post_action_pull(
        executor, **kwargs
    )
    executor.execute.side_effect = lambda **kwargs: ExecuteInternal.execute(executor, **kwargs)
    executor.write.side_effect = lambda path, text, **kwargs: path.write_text(
        (path.read_text() if path.exists() else '') + text
    )
    executor.extract_results.side_effect = lambda inv, log: [
        Result(name=inv.test.name, result=ResultOutcome.PASS)
    ]
    invocation.guest.facts.is_superuser = True
    invocation.guest.reconnect.return_value = True
    invocation.guest.reboot.return_value = True
    invocation.__dict__['pidfile'] = MagicMock()
    invocation.pidfile.create_wrappers.return_value = (Path('/inner'), Path('/outer'))
    invocation.test.restart_on_exit_code = [255]
    invocation.test.restart_max_count = 2
    monkeypatch.setattr(invocation, 'invoke_internal_checks', MagicMock(return_value=[]))
    topology = MagicMock()
    topology.push.return_value = Environment()
    monkeypatch.setattr('tmt.steps.Topology', MagicMock(return_value=topology))
    monkeypatch.setattr('tmt.steps.execute.internal.UpdatableMessage', MagicMock())
    monkeypatch.setattr('tmt.steps.execute.internal.ResultRenderer', MagicMock())
    return executor


def set_attempts(
    invocation: Invocation, monkeypatch: pytest.MonkeyPatch, codes: list[int]
) -> None:
    iterator = iter(codes)

    def invoke(*args: Any, **kwargs: Any) -> CommandOutput:
        with invocation.stopwatch:
            invocation.return_code = next(iterator)
        return CommandOutput('test output\n', None)

    monkeypatch.setattr(invocation, 'invoke_test', MagicMock(side_effect=invoke))


def test_recovery_pulls_and_classifies_before_push(
    invocation: Invocation,
    executor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    root_logger: Logger,
) -> None:
    events: list[str] = []
    snapshots = iter(
        [snapshot(), snapshot('after', [dump()]), snapshot('after'), snapshot('after')]
    )

    def inspect(*args: Any, **kwargs: Any) -> dict[str, Any]:
        events.append('inspect')
        return next(snapshots)

    monkeypatch.setattr(crash, '_inspect', inspect)
    invocation.guest.reconnect.side_effect = lambda *args: events.append('reconnect') or True
    invocation.guest.pull.side_effect = lambda **kwargs: events.append('pull')
    invocation.guest.push.side_effect = lambda **kwargs: events.append(
        'push-report' if 'source' in kwargs else 'push'
    )
    set_attempts(invocation, monkeypatch, [255, 0])
    ExecuteInternal._run_tests(executor, guest=invocation.guest, logger=root_logger)
    first = events.index('reconnect')
    assert events[first : first + 3] == ['reconnect', 'pull', 'pull']
    assert events.index('inspect', first) < events.index('push', first)
    assert invocation.guest.reconnect.call_count == 1
    assert len(invocation.check_results) == 2
    assert invocation.check_results[0].result == ResultOutcome.FAIL
    assert invocation.check_results[1].result == ResultOutcome.PASS
    assert invocation.check_results[0].log[0] != invocation.check_results[1].log[0]
    assert len(executor._results) == 1
    assert all(
        (invocation.step_workdir / log).exists()
        for result in invocation.check_results
        for log in result.log
    )


@pytest.mark.parametrize('exhausted', ['restart', 'duration'])
def test_exhausted_budget_keeps_last_crash_evidence(
    invocation: Invocation,
    executor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    root_logger: Logger,
    exhausted: str,
) -> None:
    monkeypatch.setattr(
        crash, '_inspect', MagicMock(side_effect=[snapshot(), snapshot('after', [dump()])])
    )
    set_attempts(invocation, monkeypatch, [255])
    if exhausted == 'restart':
        invocation.test.restart_max_count = 0
    else:
        invocation.__dict__['deadline'] = Deadline.from_seconds(0)
    ExecuteInternal._run_tests(executor, guest=invocation.guest, logger=root_logger)
    invocation.guest.reconnect.assert_called_once()
    assert invocation.guest.pull.call_count == 4
    invocation.guest.push.assert_called_once()
    assert executor._results[0].result == ResultOutcome.ERROR
    assert invocation.check_results[0].result == ResultOutcome.FAIL
    if exhausted == 'restart':
        assert any(isinstance(error, RestartMaxAttemptsError) for error in invocation.exceptions)
    else:
        assert invocation.return_code == ProcessExitCodes.TIMEOUT


def test_reboot_request_precedes_restart_limit(
    invocation: Invocation,
    executor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    root_logger: Logger,
) -> None:
    monkeypatch.setattr(
        crash,
        '_inspect',
        MagicMock(
            side_effect=[
                snapshot(),
                snapshot(),
                snapshot('after'),
                snapshot('after'),
            ]
        ),
    )
    invocation.test.restart_max_count = 0
    set_attempts(invocation, monkeypatch, [255, 0])

    def pull(**kwargs: Any) -> None:
        if invocation.return_code == 255 and invocation.reboot.reboot_counter == 0:
            invocation.reboot.request_path.write_text('{}')

    invocation.guest.pull.side_effect = pull
    ExecuteInternal._run_tests(executor, guest=invocation.guest, logger=root_logger)
    invocation.guest.reboot.assert_called_once()
    assert invocation.reboot.reboot_counter == 1
    assert len(invocation.check_results) == 2
    assert not invocation.exceptions
    assert (
        json.loads((invocation.test_data_path / crash.REPORT_FILENAME).read_text())['reports'][0][
            'classification'
        ]
        == 'expected-reboot'
    )


def test_unrecovered_guest_finalizes_without_late_pull(
    invocation: Invocation,
    executor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    root_logger: Logger,
) -> None:
    monkeypatch.setattr(crash, '_inspect', MagicMock(return_value=snapshot()))
    invocation.guest.reconnect.return_value = False
    set_attempts(invocation, monkeypatch, [255])
    with pytest.raises(AbortStep, match='Guest recovery failed'):
        ExecuteInternal._run_tests(executor, guest=invocation.guest, logger=root_logger)
    invocation.guest.pull.assert_not_called()
    assert len(executor._results) == 1
    assert invocation.check_results[0].result == ResultOutcome.ERROR
    assert (invocation.test_data_path / crash.REPORT_FILENAME).exists()


def test_recovery_does_not_opt_generic_test_into_restart(
    invocation: Invocation,
    executor: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    root_logger: Logger,
) -> None:
    monkeypatch.setattr(
        crash, '_inspect', MagicMock(side_effect=[snapshot(), snapshot('after', [dump()])])
    )
    invocation.test.restart_on_exit_code = []
    set_attempts(invocation, monkeypatch, [255])
    ExecuteInternal._run_tests(executor, guest=invocation.guest, logger=root_logger)
    invocation.guest.reconnect.assert_called_once()
    assert invocation.restart.restart_counter == 0
    assert len(invocation.check_results) == 1
