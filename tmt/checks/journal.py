import datetime
import re
from re import Pattern
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.utils
from tmt.checks import Check, CheckPlugin, _RawCheck, provides_check
from tmt.container import container, field
from tmt.result import CheckResult, ResultOutcome, save_failures
from tmt.utils import Path, ShellScript, format_timestamp, render_command_report

if TYPE_CHECKING:
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest

#: The filename of the final check report file.
TEST_POST_JOURNAL_FILENAME = 'journal.txt'

#: The filename of the "mark" file ``journalctl`` on the guest.
JOURNALCTL_CURSOR_FILENAME = 'journal-cursor.txt'

# Can be set in /etc/systemd/journald.conf.d/
# See `man journald.conf`
JOURNAL_CONFIG = """[Journal]
Storage=persistent
Compress=yes
"""

DEFAULT_FAILURE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r'Call Trace:',
        r'\ssegfault\s',
    ]
]


@container
class JournalCheck(Check):
    failure_pattern: list[Pattern[str]] = field(
        default_factory=lambda: DEFAULT_FAILURE_PATTERNS[:],
        help="""
             List of regular expressions to look for in ``journal``
             log. If any of patterns is found, ``journal`` check will
             report ``fail`` result.
             """,
        metavar='PATTERN',
        normalize=tmt.utils.normalize_pattern_list,
        exporter=lambda patterns: [pattern.pattern for pattern in patterns],
        serialize=lambda patterns: [pattern.pattern for pattern in patterns],
        unserialize=lambda serialized: [re.compile(pattern) for pattern in serialized],
    )
    ignore_pattern: list[Pattern[str]] = field(
        default_factory=list,
        help="""
             Optional list of regular expressions to ignore in journal log.
             If a log entry matches any of these patterns, it will be ignored
             and not cause a failure.
             """,
        metavar='PATTERN',
        normalize=tmt.utils.normalize_pattern_list,
        exporter=lambda patterns: [pattern.pattern for pattern in patterns],
        serialize=lambda patterns: [pattern.pattern for pattern in patterns],
        unserialize=lambda serialized: [re.compile(pattern) for pattern in serialized],
    )
    dmesg: bool = field(default=False, help='Check only kernel messages.')
    unit: Optional[str] = field(default=None, help='Check logs for a specific systemd unit.')
    identifier: Optional[str] = field(
        default=None, help='Check logs for a specific syslog identifier.'
    )
    priority: Optional[str] = field(
        default=None, help='Filter by priority (e.g. ``err``, ``warning``).'
    )

    # TODO: fix `to_spec` of `Check` to support nested serializables
    def to_spec(self) -> _RawCheck:
        spec = super().to_spec()

        spec['failure-pattern'] = [  # type: ignore[reportGeneralTypeIssues,typeddict-unknown-key,unused-ignore]
            pattern.pattern for pattern in self.failure_pattern
        ]
        spec['ignore-pattern'] = [  # type: ignore[reportGeneralTypeIssues,typeddict-unknown-key,unused-ignore]
            pattern.pattern for pattern in self.ignore_pattern
        ]

        return spec

    def to_minimal_spec(self) -> _RawCheck:
        return self.to_spec()

    def _extract_failures(self, text: str) -> list[str]:
        return [
            line
            for line in text.splitlines()
            if any(pattern.search(line) for pattern in self.failure_pattern)
            and not any(pattern.search(line) for pattern in self.ignore_pattern)
        ]

    def _configure_journal(self, guest: "Guest", logger: tmt.log.Logger) -> None:
        """
        Try configure journal storage.

        Non-privileged users might not have permission to change the config,
        while being able to use journalctl
        """
        try:
            guest.execute(
                ShellScript("mkdir -p /etc/systemd/journald.conf.d")
                & ShellScript(
                    f"echo '{JOURNAL_CONFIG}' > /etc/systemd/journald.conf.d/50-tmt.conf",
                ),
                silent=True,
            )
            return
        except tmt.utils.RunError:
            logger.debug("Unable to configure journal directly, trying with sudo")

        # If failed and not root, try with sudo
        if guest.facts.is_superuser is False:
            try:
                guest.execute(
                    ShellScript("sudo mkdir -p /etc/systemd/journald.conf.d")
                    & ShellScript(
                        f"echo '{JOURNAL_CONFIG}' | sudo tee "
                        "/etc/systemd/journald.conf.d/50-tmt.conf > /dev/null"
                    ),
                    silent=True,
                )
                logger.debug("Configured journal with sudo")
                return
            except tmt.utils.RunError:
                logger.debug(
                    "Unable to configure journal even with sudo, continuing with default settings"
                )
        else:
            logger.debug("Unable to configure journal, continuing with default settings")

    def _get_cursor_file(self, invocation: 'TestInvocation') -> Path:
        return invocation.check_files_path / JOURNALCTL_CURSOR_FILENAME

    def _create_journalctl_cursor(
        self, invocation: 'TestInvocation', logger: tmt.log.Logger
    ) -> None:
        """
        Save a mark for ``journalctl`` in a file on the guest
        """
        # Determine if we need sudo
        need_sudo = invocation.guest.facts.is_superuser is False
        sudo_prefix = "sudo " if need_sudo else ""

        try:
            # Create the cursor file
            invocation.guest.execute(ShellScript(f"mkdir -p {invocation.check_files_path!s}"))

            # Save cursor for journalctl
            cursor_file = self._get_cursor_file(invocation)
            invocation.guest.execute(
                ShellScript(
                    f"[ -f '{cursor_file}' ] || {sudo_prefix}journalctl \
                    -n 0 --show-cursor --cursor-file={cursor_file}"
                )
            )
        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to create journalctl cursor: {exc}")

    def _save_journal(
        self, invocation: 'TestInvocation', logger: tmt.log.Logger
    ) -> tuple[ResultOutcome, list[Path]]:
        assert invocation.phase.step.workdir is not None  # narrow type

        timestamp = format_timestamp(datetime.datetime.now(datetime.timezone.utc))
        path = invocation.check_files_path / TEST_POST_JOURNAL_FILENAME

        # Build journalctl command
        options: list[str] = []
        if self.dmesg:
            options.append('--dmesg')
        if self.unit:
            options.append(f'--unit={self.unit}')
        if self.identifier:
            options.append(f'--identifier={self.identifier}')
        if self.priority:
            options.append(f'--priority={self.priority}')

        cursor_file = self._get_cursor_file(invocation)
        script = ShellScript(
            f"journalctl --cursor-file={cursor_file} {' '.join(options)} --boot=all"
        )

        if not invocation.guest.facts.is_superuser:
            script = ShellScript(f'sudo {script.to_shell_command()}')

        try:
            outcome = ResultOutcome.PASS
            output = invocation.guest.execute(script, silent=True)

        except tmt.utils.RunError as exc:
            outcome = ResultOutcome.ERROR
            output = exc.output

        failures = self._extract_failures(output.stdout or '')
        if failures and outcome == ResultOutcome.PASS:
            outcome = ResultOutcome.FAIL

        # Use render_command_report but with append mode for multiple reports
        report_content = list(render_command_report(label='journal log', output=output))

        # Add timestamp header and append to file like original implementation
        full_report = [f'# Reported at {timestamp}', *report_content]
        invocation.phase.write(path, '\n'.join(full_report), mode='a')

        log_paths = [
            path.relative_to(invocation.phase.step.workdir),
            save_failures(invocation, invocation.check_files_path, failures),
        ]

        return outcome, log_paths


@provides_check('journal')
class Journal(CheckPlugin[JournalCheck]):
    #
    # This plugin docstring has been reviewed and updated to follow
    # our documentation best practices. When changing it, please make
    # sure new changes are following them as well.
    #
    # https://tmt.readthedocs.io/en/stable/contribute.html#docs
    #
    """
    Check messages in journal log recorded during the test.

    This check uses ``journalctl`` to capture log messages created
    during the test execution. It uses cursors to precisely pinpoint
    the start and end of the logging period.

    Example usage:

    .. code-block:: yaml

        check:
          - how: journal
            # Check only kernel messages
            dmesg: true

    .. code-block:: yaml

        check:
          - how: journal
            # Check messages from a specific systemd unit
            unit: httpd.service
            # Filter by priority
            priority: err

    Check will identify patterns that signal kernel crashes and
    core dumps, and when detected, it will report a failed result.
    It is possible to define custom patterns for failures and
    messages to ignore:

    .. code-block:: yaml

        check:
          - how: journal
            failure-pattern:
              # These are default patterns
              - 'Call Trace:'
              - '\\ssegfault\\s'

              # More patterns to look for
              - '\\[Firmware Bug\\]'
            ignore-pattern:
              - 'a known harmless error message'

    .. versionadded:: 1.54.0
    """

    _check_class = JournalCheck

    @classmethod
    def before_test(
        cls,
        *,
        check: 'JournalCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if not invocation.guest.facts.has_systemd:
            return [CheckResult(name='journal', result=ResultOutcome.SKIP)]

        check._configure_journal(invocation.guest, logger)
        check._create_journalctl_cursor(invocation, logger)
        return []

    @classmethod
    def after_test(
        cls,
        *,
        check: 'JournalCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if not invocation.guest.facts.has_systemd:
            return [CheckResult(name='journal', result=ResultOutcome.SKIP)]

        if not invocation.is_guest_healthy:
            return [CheckResult(name='journal', result=ResultOutcome.SKIP)]

        outcome, paths = check._save_journal(invocation, logger)
        return [CheckResult(name='journal', result=outcome, log=paths)]
