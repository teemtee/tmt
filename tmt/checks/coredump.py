import re
from re import Pattern
from time import sleep
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckEvent, CheckPlugin, _RawCheck, provides_check
from tmt.container import container, field
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import Command, Path, ShellScript

if TYPE_CHECKING:
    import tmt.base
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest


COREDUMP_TIMESTAMP_FILENAME = "coredump-timestamp"

# Can be set in /etc/coredumpct.conf.d/
# See `man coredump.conf`
COREDUMP_CONFIG = """[Coredump]
Storage=external
Compress=yes
"""


@container
class CoredumpCheck(Check):
    """Configuration for the coredump check."""

    # Patterns to ignore in crash reports
    ignore_patterns: list[Pattern[str]] = field(
        default_factory=list,
        help="""
             Optional list of regular expressions to ignore in crash reports.
             If a crash report matches any of these patterns, it will be ignored
             and not cause a failure. Any other crashes will still cause the test
             to fail. If no patterns are specified, any crash will cause a failure.
             """,
        metavar="PATTERN",
        normalize=tmt.utils.normalize_pattern_list,
        exporter=lambda patterns: [pattern.pattern for pattern in patterns],
        serialize=lambda patterns: [pattern.pattern for pattern in patterns],
        unserialize=lambda serialized: [re.compile(pattern) for pattern in serialized],
    )

    # Internal flag to track if we can run coredumpctl on the host
    is_available: bool = True

    def to_spec(self) -> _RawCheck:
        """Convert to raw specification."""
        spec = super().to_spec()

        spec["ignore-patterns"] = [  # type: ignore[reportGeneralTypeIssues,typeddict-unknown-key,unused-ignore]
            pattern.pattern for pattern in self.ignore_patterns
        ]

        return spec

    def to_minimal_spec(self) -> _RawCheck:
        """Convert to minimal raw specification."""
        return self.to_spec()

    def _configure_coredump(self, guest: "Guest", logger: tmt.log.Logger) -> None:
        """
        Try configure coredump storage.

        Non-privileged users might not have permission to change the config,
        while being able to use coredumpctl
        """
        try:
            guest.execute(
                ShellScript("mkdir -p /etc/systemd/coredump.conf.d")
                and ShellScript(
                    f"echo '{COREDUMP_CONFIG}' > /etc/systemd/coredump.conf.d/50-tmt.conf"
                )
            )

        except tmt.utils.RunError:
            logger.debug("Unable to configure coredump, continuing with default settings")

    def _check_coredump_available(self, guest: "Guest", logger: tmt.log.Logger) -> bool:
        """
        Check if coredump functionality is available and usable.

        Checks for:
        1. systemd availability through guest facts
        2. coredumpctl command exists
        3. systemd-coredump.socket is active or can be activated
        4. Has sufficient permissions to access coredump data

        :returns: True if coredump is available and we have necessary permissions,
                 False otherwise.
        """
        # We need systemd for coredump functionality
        if not guest.facts.has_systemd:
            logger.debug("systemd not available, skipping coredump check")
            return False

        # Check if coredumpctl is present
        try:
            guest.execute(ShellScript("coredumpctl --version"), silent=True)
        except tmt.utils.RunError:
            logger.debug("coredumpctl command not found")
            return False

        # Check if systemd-coredump.socket is active
        try:
            # Try activating the socket if it's not already active
            guest.execute(
                ShellScript(
                    "systemctl is-active systemd-coredump.socket || "
                    "systemctl start systemd-coredump.socket"
                ),
                silent=True,
            )
        except tmt.utils.RunError:
            logger.debug("Unable to access or start systemd-coredump.socket")
            return False

        # Check if we can access coredump files
        try:
            guest.execute(ShellScript("coredumpctl list --no-pager"), silent=True)
            return True
        except tmt.utils.RunError:
            logger.debug("Cannot access coredump data - permission issues")
            return False

    def _check_for_crashes(
        self, guest: "Guest", logger: tmt.log.Logger, check_files_path: str, start_time: str
    ) -> bool:
        """Check if any crashes have been detected."""
        try:
            # Get list of all crashes since test start
            # Not using `--json` as it's not available on el8.
            output = guest.execute(
                Command(
                    "coredumpctl", "list", "--no-legend", "--no-pager", f"--since={start_time}"
                )
            ).stdout

            if not output:
                return False

            # Process each crash entry
            has_crashes = False
            for line in output.splitlines():
                fields = line.split()

                pid = fields[4]
                sig = fields[7]
                corefile = fields[8]
                exe = fields[9].replace("/", "_")

                # Get detailed info for this crash
                crash_info = guest.execute(
                    Command("coredumpctl", "info", "--no-pager", pid)
                ).stdout

                if not crash_info:
                    logger.debug(f"No crash info available for PID {pid}")
                    continue

                # Skip if this crash matches any ignore pattern
                if self.ignore_patterns and any(
                    pattern.search(crash_info) for pattern in self.ignore_patterns
                ):
                    logger.debug(f"Ignoring crash due to pattern match in: {crash_info}")
                    continue

                # Save the crash info
                info_file = f"{check_files_path}/dump.{exe}_{sig}_{pid}.txt"
                guest.execute(
                    ShellScript(f"sh -c coredumpctl info --no-pager {pid} > {info_file}")
                )
                logger.debug(f"Saved crash info to {info_file}")

                # Try to save the coredump if available
                if corefile not in ("none", "missing"):
                    dump_file = f"{check_files_path}/dump.{exe}_{sig}_{pid}.core"
                    try:
                        guest.execute(
                            ShellScript(f"coredumpctl dump --no-pager -o {dump_file} {pid}")
                        )
                        logger.debug(f"Saved coredump to {dump_file}")
                    except tmt.utils.RunError as exc:
                        logger.debug(f"Failed to save coredump for PID {pid}: {exc}")
                else:
                    logger.debug(f"Skipping dump for PID {pid}, corefile status: {corefile}")

                # This is a non-ignored crash
                has_crashes = True

            return has_crashes

        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to check for crashes: {exc}")
            return False

    def _check_coredump(
        self, invocation: "TestInvocation", event: CheckEvent, logger: tmt.log.Logger
    ) -> tuple[ResultOutcome, list[Path]]:
        """
        Check coredump status and return appropriate result.

        :returns: A tuple of (outcome, log_files) where log_files is a list of
                 paths to files with coredump information.
        """
        log_files: list[Path] = []

        # Check for crash reports in after_test
        output = invocation.guest.execute(Command("cat", self.coredump_timestamp_filepath)).stdout

        if not output:
            logger.debug("Failed to read timestamp file")
            return ResultOutcome.ERROR, log_files

        start_time = output.strip()

        # Check for crashes
        has_crashes = self._check_for_crashes(
            invocation.guest, logger, str(invocation.check_files_path), start_time
        )

        # Get list of generated files
        try:
            files_output = invocation.guest.execute(
                Command("find", str(invocation.check_files_path), "-type", "f")
            ).stdout

            if files_output:
                for file_path in files_output.splitlines():
                    path = Path(file_path)
                    if path.exists() and invocation.phase.step.workdir:
                        rel_path = path.relative_to(invocation.phase.step.workdir)
                        log_files.append(rel_path)
        except tmt.utils.RunError:
            logger.debug("Failed to list coredump files")

        if has_crashes:
            return ResultOutcome.FAIL, log_files

        return ResultOutcome.PASS, log_files

    def _create_coredump_timestamp(self, invocation: "TestInvocation") -> bool:
        self.coredump_timestamp_filepath = (
            invocation.check_files_path / COREDUMP_TIMESTAMP_FILENAME
        )
        # Create timestamp directory and store current time for --since filtering
        if not invocation.guest.execute(
            ShellScript(f"mkdir -p {invocation.check_files_path}")
            and ShellScript(f"date '+%Y-%m-%d %H:%M:%S' > {self.coredump_timestamp_filepath}")
        ):
            return False
        return True


# TODO: Enable hints when PR #3498 is merged
# @provides_check(
#     "coredump",
#     hints={  # type: ignore[call-arg]
#         "not-available": """
#             Coredump detection was skipped because coredumpctl is not available or has
#             insufficient privileges.


#             The coredump check requires systemd-coredump to be installed and the
#             systemd-coredump.socket to be active. Additionally, the user must have
#             sufficient permissions to access coredump data.
#             """
#     },
# )
@provides_check("coredump")
class Coredump(CheckPlugin[CoredumpCheck]):
    """
    Check for system crashes using coredump.

    The check monitors for any crashes caught by systemd-coredump during test
    execution. This includes segmentation faults and other crashes that produce
    core dumps. By default, any crash will cause the test to fail.

    Example config with optional ignore patterns:

    .. code-block:: yaml

        check:
          - how: coredump
            ignore-patterns:
              - 'Process.*\\(sleep\\).*dumped core'  # Ignore sleep crashes
              - 'Package: ddcutil/2.1.2-2.fc41'      # Ignore dumps of a specific package

    The patterns are matched against the full coredumpctl info output, which includes
    fields like Process, Command Line, Signal, etc. You can use 'coredumpctl info'
    to see the available fields and their format.

    .. versionadded:: 1.41
    """

    _check_class = CoredumpCheck

    @classmethod
    def before_test(
        cls,
        *,
        check: "CoredumpCheck",
        invocation: "TestInvocation",
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        """Check for crashes before the test starts."""

        # TODO: Uncomment when PR #3498 is merged
        # from tmt.utils.hints import get_hints

        if not check._check_coredump_available(invocation.guest, logger):
            logger.debug("coredump not available, skipping..")
            check.is_available = False
            # TODO: Add note when PR #3498 is merged
            # return [CheckResult(
            #     name="coredump",
            #     result=ResultOutcome.SKIP,
            #     note=[hint.summary_ref
            #            for hint in get_hints('test-checks/coredump/not-available')]
            # )]
            return [CheckResult(name="coredump", result=ResultOutcome.SKIP)]

        # Initialize outcome to ERROR in case timestamp creation fails
        outcome = ResultOutcome.ERROR
        log_files: list[Path] = []

        if check._create_coredump_timestamp(invocation):
            check._configure_coredump(invocation.guest, logger)
            outcome, log_files = check._check_coredump(invocation, CheckEvent.BEFORE_TEST, logger)

        return [CheckResult(name="coredump", result=outcome, log=log_files)]

    @classmethod
    def after_test(
        cls,
        *,
        check: "CoredumpCheck",
        invocation: "TestInvocation",
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        """Check for crashes after the test finishes."""
        # TODO: Uncomment when PR #3498 is merged
        # from tmt.utils.hints import get_hints

        # Skip if coredumpctl is not available, as detected in before-test
        sleep(1)
        if not check.is_available:
            # TODO: Add note when PR #3498 is merged
            # return [CheckResult(
            #     name="coredump",
            #     result=ResultOutcome.SKIP,
            #     note=[hint.summary_ref for hint in get_hints(
            # 'test-checks/coredump/not-available')]
            # )]
            return [CheckResult(name="coredump", result=ResultOutcome.SKIP)]

        if not invocation.is_guest_healthy:
            # TODO: Add note when PR #3498 is merged
            # return [CheckResult(
            #     name="coredump",
            #     result=ResultOutcome.SKIP,
            #     note=[hint.summary_ref for hint in get_hints('guest-not-healthy')]
            # )]
            return [CheckResult(name="coredump", result=ResultOutcome.SKIP)]

        outcome, log_files = check._check_coredump(invocation, CheckEvent.AFTER_TEST, logger)
        return [CheckResult(name="coredump", result=outcome, log=log_files)]
