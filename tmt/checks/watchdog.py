import dataclasses
import datetime
import re
import threading
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.steps.provision.artemis
import tmt.steps.provision.connect
import tmt.steps.provision.local
import tmt.steps.provision.mrack
import tmt.steps.provision.podman
import tmt.steps.provision.testcloud
import tmt.utils
from tmt.checks import Check, CheckPlugin, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import Path, field, format_timestamp, render_run_exception_streams

if TYPE_CHECKING:
    from tmt.steps.execute import TestInvocation

PING_OUTPUT_PATTERN = re.compile(
    r'(?m)(?P<transmitted>\d+) packets transmitted, (?P<received>\d+) received')
SSH_PING_OUTPUT_PATTERN = re.compile(r'Ncat: Connected')

# TODO: do not use the list of classes, it's hard to maintain.
# Tracked in https://github.com/teemtee/tmt/issues/2739
PINGABLE_GUEST_CLASSES: tuple[type[tmt.steps.provision.Guest], ...] = (
    tmt.steps.provision.artemis.GuestArtemis,
    tmt.steps.provision.connect.GuestConnect,
    tmt.steps.provision.mrack.GuestBeaker,
    # TODO: is there a way to ping the VM instead of localhost?
    # Tracked in https://github.com/teemtee/tmt/issues/2738
    # tmt.steps.provision.testcloud.GuestTestcloud
    )

SSH_PINGABLE_GUEST_CLASSES: tuple[type[tmt.steps.provision.Guest], ...] = (
    tmt.steps.provision.GuestSsh,
    tmt.steps.provision.local.GuestLocal
    )


REPORT_FILENAME = 'tmt-watchdog.txt'


def render_report_path(invocation: 'TestInvocation') -> Path:
    """ Render path to a watchdog report file from necessary components """

    return invocation.check_files_path / REPORT_FILENAME


def report_progress(
        log: Path,
        check_name: str,
        report: Iterable[str],
        command_output: Optional[str] = None) -> None:
    """
    Add new report into a report file.

    :param log: path to the report file.
    :param report: iterable of report lines to add. Each line is emitted on its
        own line in the file.
    :param command_output: if set, the string is added to the report file once
        ``report`` lines are written into it.
    """

    timestamp = format_timestamp(datetime.datetime.now(datetime.timezone.utc))

    with open(log, mode='a') as f:
        f.write(f'# {check_name} reported at {timestamp}\n')

        for line in report:
            f.write(line)
            f.write('\n')

        if command_output:
            f.write('\n')
            f.write(command_output)

        f.write('\n')


@dataclasses.dataclass
class GuestContext:
    """ Per-guest watchdog context """

    #: Current number of failed watchdog checks.
    ping_failures: int = 0
    ssh_ping_failures: int = 0

    #: If set, contains a daemonized thread running the watchdog checks.
    thread: Optional[threading.Thread] = None

    #: As long as this field is set to ``True``, the watchdog will run its
    #: internal loop and run relevant checks. It is unset when terminating
    #: the watchdog check to notify the thread it's time to quit.
    keep_running: bool = True


@dataclasses.dataclass
class WatchdogCheck(Check):
    interval: int = field(
        default=60,
        help='How often should the watchdog run, in seconds.')

    reboot: bool = field(
        default=False,
        help='If enabled, watchdog would reboot the guest after enough failed probes.')

    ping: bool = field(
        default=False,
        help="If enabled, watchdog would probe guest's responsiveness with ICMP packets.")
    ping_packets: int = field(
        default=1,
        help='How many ICMP packates to send as one probe.')
    ping_threshold: int = field(
        default=10,
        help='How many failed ping probes before taking any further action.')

    ssh_ping: bool = field(
        default=False,
        help="""
             If enabled, watchdog would probe guest's responsiveness by connecting
             to its SSH port.
             """)
    ssh_ping_threshold: int = field(
        default=10,
        help='How many failed SSH connections before taking any further action.')

    def notify(self, invocation: 'TestInvocation', logger: tmt.log.Logger) -> None:
        """ Notify invocation that hard reboot is required """

        if not self.reboot:
            return

        invocation.hard_reboot_requested = True
        invocation.terminate_process(logger=logger)

    def do_ping(
            self,
            invocation: 'TestInvocation',
            guest_context: GuestContext,
            logger: tmt.log.Logger) -> None:
        """ Perform a ping check """

        logger.debug('pinging', level=4)

        log = render_report_path(invocation)

        def _fail_parse_error(ping_output: str) -> None:
            """ Handle unparsable ``ping`` output """

            logger.fail('failed to parse ping output')

            guest_context.ping_failures += 1

            report_progress(
                log,
                'ping',
                [
                    '# failed to parse ping output',
                    f'# failed {guest_context.ping_failures} of {self.ping_threshold} allowed',
                    ],
                command_output=ping_output
                )

        def _fail_lost_packets(ping_output: str, transmitted: int, received: int) -> None:
            """ Handle missing response packets """

            logger.fail(f'not all packets returned: {transmitted=} {received=}')

            guest_context.ping_failures += 1

            report_progress(
                log,
                'ping',
                [
                    '# not all packets returned',
                    f'# failed {guest_context.ping_failures} of {self.ping_threshold} allowed',
                    ],
                command_output=ping_output
                )

        def _success(ping_output: str) -> None:
            """ Handle successful response """

            logger.verbose('Received successful response to ping.', level=2)

            report = [
                '# successful response'
                ]

            if guest_context.ping_failures != 0:
                report.append(f'# replenished failure budget back to {self.ping_threshold}')

            guest_context.ping_failures = 0

            report_progress(
                log,
                'ping',
                report,
                command_output=ping_output
                )

        def _handle_output(ping_output: str) -> None:
            """ Process ``ping`` output and decide on its outcome """

            match = PING_OUTPUT_PATTERN.search(ping_output)

            if match is None:
                _fail_parse_error(ping_output)

            else:
                groups = match.groupdict()

                transmitted = int(groups['transmitted'])
                received = int(groups['received'])

                if transmitted != received:
                    _fail_lost_packets(ping_output, transmitted, received)

                else:
                    _success(ping_output)

            logger.debug(
                f'failed {guest_context.ping_failures}'
                f' of {self.ping_threshold} allowed')

            if guest_context.ping_failures >= self.ping_threshold:
                logger.fail(f'exhausted {self.ping_threshold} ping attempts')

                self.notify(invocation, logger)

        try:
            assert invocation.guest.primary_address is not None  # narrow type

            output = tmt.utils.Command('ping',
                                       '-c',
                                       str(self.ping_packets),
                                       invocation.guest.primary_address) .run(cwd=Path.cwd(),
                                                                              stream_output=False,
                                                                              logger=logger)

            _handle_output(output.stdout or '')

        except tmt.utils.RunError as exc:
            if exc.returncode == 1:
                _handle_output(exc.stdout or '')

            else:
                _handle_output('\n'.join(render_run_exception_streams(exc.stdout, exc.stderr)))

    def do_ssh_ping(
            self,
            invocation: 'TestInvocation',
            guest_context: GuestContext,
            logger: tmt.log.Logger) -> None:
        """ Perform a "SSH ping" check """

        assert isinstance(invocation.guest, tmt.steps.provision.GuestSsh)

        logger.debug('checking SSH port', level=4)

        log = render_report_path(invocation)

        def _fail_unknown(ncat_output: str) -> None:
            """ Handle unknown failures """

            logger.fail('unknown error')

            guest_context.ssh_ping_failures += 1

            report_progress(log,
                            'ssh-ping',
                            [
                                '# unknown error',
                                f'# failed {guest_context.ssh_ping_failures}'
                                f' of {self.ssh_ping_threshold} allowed',
                                ],
                            command_output=ncat_output)

        def _fail_connection_refused(ncat_output: str) -> None:
            """ Handle failed connection """

            logger.fail('connection refused')

            guest_context.ssh_ping_failures += 1

            report_progress(log,
                            'ssh-ping',
                            [
                                '# connection refused',
                                f'# failed {guest_context.ssh_ping_failures}'
                                f' of {self.ssh_ping_threshold} allowed',
                                ],
                            command_output=ncat_output)

        def _success(ncat_output: str) -> None:
            """ Handle successful response """

            logger.verbose('Received successful response to SSH ping.', level=2)

            report = [
                '# successful response'
                ]

            if guest_context.ssh_ping_failures != 0:
                report.append(f'# replenished failure budget back to {self.ssh_ping_threshold}')

            guest_context.ssh_ping_failures = 0

            report_progress(
                log,
                'ssh-ping',
                report,
                command_output=ncat_output
                )

        try:
            assert invocation.guest.primary_address is not None  # narrow type

            output = tmt.utils.Command('nc',
                                       '-zv',
                                       invocation.guest.primary_address,
                                       str(invocation.guest.port or 22)) .run(cwd=Path.cwd(),
                                                                              stream_output=False,
                                                                              logger=logger)

            _success(output.stderr or '')

        except tmt.utils.RunError as exc:
            if exc.returncode == 1:
                _fail_connection_refused(exc.stderr or '')

            else:
                _fail_unknown('\n'.join(render_run_exception_streams(exc.stdout, exc.stderr)))

        logger.debug(
            f'failed {guest_context.ssh_ping_failures}'
            f' of {self.ssh_ping_threshold} allowed')

        if guest_context.ssh_ping_failures >= self.ssh_ping_threshold:
            logger.fail(f'exhausted {self.ssh_ping_threshold} SSH ping attempts')

            self.notify(invocation, logger)


@provides_check('watchdog')
class Watchdog(CheckPlugin[WatchdogCheck]):
    """
    Take various actions when guest becomes unresponsive.

    Watchdog runs selected probes every now and then, and when a given
    number of `probes` fail, watchdog would run one or more of the
    predefined `actions`.

    Check comes with two probes, "ping" and "SSH ping", and single
    action, "reboot".

    * "ping" uses the classic ICMP echo to check whether the guest is
      still up and running,
    * "SSH ping" tries to establish SSH connection,
    * "reboot" action issues a hard reboot of the guest.

    .. warning::

        Be aware that this feature may be limited depending on how the
        guest was provisioned. See :ref:`/plugins/provision/hard-reboot`.

    Each probe has a "budget" of allowed failures, and when it runs out,
    the action is taken. A successful probe replenishes its budget to
    the original level.

    Multiple probes can be enabled at the same time, for the action to
    happen it's enough if just one of them runs out of its budget.

    .. code-block:: yaml

        check:
          - how: watchdog
            ping: true
            reboot: true

    .. code-block:: yaml

        check:
          - how: watchdog

            # Use only SSH ping.
            ping: false
            ssh-ping: true

            # Try every 5 minutes, allow 7 failed attempts, and reboot
            # the guest when we run out of attempts.
            interval: 300
            reboot: true
            ssh-ping-threshold: 7

    .. versionadded:: 1.32
    """

    _check_class = WatchdogCheck

    @classmethod
    def before_test(
            cls,
            *,
            check: WatchdogCheck,
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:

        # Setup a logger
        watchdog_logger = logger.clone()
        watchdog_logger.labels.append('watchdog')

        # Create a guest context for the guest we've been given
        invocation.check_data[check.how] = GuestContext()

        guest_context: GuestContext = invocation.check_data[check.how]

        if check.ping and not isinstance(invocation.guest, PINGABLE_GUEST_CLASSES):
            watchdog_logger.warning('Ping against this guest is not supported, disabling.')

            check.ping = False

        if check.ssh_ping and not isinstance(invocation.guest, SSH_PINGABLE_GUEST_CLASSES):
            watchdog_logger.warning('SSH ping against this guest is not supported, disabling.')

            check.ssh_ping = False

        def watchdog(guest_context: GuestContext) -> None:
            """ Watchdog thread code """

            tid = threading.get_ident()

            watchdog_logger.debug(f'Watchdog starts in thread {tid}')

            while guest_context.keep_running:
                if check.ping:
                    check.do_ping(invocation, guest_context, watchdog_logger)

                if check.ssh_ping:
                    check.do_ssh_ping(invocation, guest_context, watchdog_logger)

                time.sleep(check.interval)

            watchdog_logger.debug(f'Watchdog finished in thread {tid}')

        guest_context.thread = threading.Thread(
            target=watchdog,
            args=(guest_context,),
            name=f'watchdog-{invocation.guest.name}',
            daemon=True)

        guest_context.thread.start()

        return []

    @classmethod
    def after_test(
            cls,
            *,
            check: WatchdogCheck,
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:

        watchdog_logger = logger.clone()
        watchdog_logger.labels.append('watchdog')

        guest_context: GuestContext = invocation.check_data[check.how]

        if guest_context.thread:
            watchdog_logger.debug(f'Terminating watchdog in thread {guest_context.thread.ident}')

            guest_context.keep_running = False
            guest_context.thread.join()

            guest_context.thread = None

        assert invocation.phase.step.workdir is not None  # narrow type

        return [
            CheckResult(
                name='watchdog',
                result=ResultOutcome.PASS,
                log=[render_report_path(invocation).relative_to(invocation.phase.step.workdir)])]
