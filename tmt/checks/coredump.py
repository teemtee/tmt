import re
from re import Pattern
from time import sleep
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.utils
from tmt.checks import Check, CheckPlugin, _RawCheck, provides_check
from tmt.container import container, field
from tmt.result import CheckResult, ResultOutcome, save_failures
from tmt.utils import Command, Path, ShellScript

if TYPE_CHECKING:
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest


COREDUMP_LAST_DUMP_FILENAME = "coredump-latest"

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
    ignore_pattern: list[Pattern[str]] = field(
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
    is_availability_reason: Optional[str] = None

    # Path to the file storing information about coredumps before test execution
    # Default is current directory, will be properly set in _save_existing_coredumps
    coredump_last_dumps_filepath: Path = field(default_factory=Path, internal=True)

    def to_spec(self) -> _RawCheck:
        """Convert to raw specification."""
        spec = super().to_spec()

        spec["ignore-pattern"] = [  # type: ignore[reportGeneralTypeIssues,typeddict-unknown-key,unused-ignore]
            pattern.pattern for pattern in self.ignore_pattern
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
                & ShellScript(
                    f"echo '{COREDUMP_CONFIG}' > /etc/systemd/coredump.conf.d/50-tmt.conf"
                )
            )
            return
        except tmt.utils.RunError:
            logger.debug("Unable to configure coredump directly, trying with sudo")

        # If failed and not root, try with sudo
        if guest.facts.is_superuser is False:
            try:
                guest.execute(
                    ShellScript("sudo mkdir -p /etc/systemd/coredump.conf.d")
                    & ShellScript(
                        f"echo '{COREDUMP_CONFIG}' | sudo tee "
                        "/etc/systemd/coredump.conf.d/50-tmt.conf > /dev/null"
                    )
                )
                logger.debug("Configured coredump with sudo")
                return
            except tmt.utils.RunError:
                logger.debug(
                    "Unable to configure coredump even with sudo, continuing with default settings"
                )
        else:
            logger.debug("Unable to configure coredump, continuing with default settings")

    def _has_coredumpctl(self, guest: "Guest", logger: tmt.log.Logger) -> bool:
        """Check if coredumpctl command is available."""
        try:
            guest.execute(ShellScript("coredumpctl --version"), silent=True)
            return True
        except tmt.utils.RunError:
            logger.debug("coredumpctl command not found")
            return False

    def _has_active_socket(self, guest: "Guest", logger: tmt.log.Logger) -> bool:
        """Check if systemd-coredump.socket is active or can be activated."""
        try:
            # Try activating the socket if it's not already active
            guest.execute(
                ShellScript(
                    "systemctl is-active systemd-coredump.socket || "
                    "systemctl start systemd-coredump.socket"
                ),
                silent=True,
            )
            return True
        except tmt.utils.RunError:
            # If the user isn't root, try with sudo
            if guest.facts.is_superuser is False:
                try:
                    guest.execute(
                        ShellScript(
                            "sudo systemctl is-active systemd-coredump.socket || "
                            "sudo systemctl start systemd-coredump.socket"
                        ),
                        silent=True,
                    )
                    logger.debug("systemd-coredump.socket activated with sudo")
                    return True
                except tmt.utils.RunError:
                    logger.debug(
                        "Unable to access or start systemd-coredump.socket, even with sudo"
                    )
                    return False
            else:
                logger.debug("Unable to access or start systemd-coredump.socket")
                return False

    def _has_required_permissions(self, guest: "Guest", logger: tmt.log.Logger) -> bool:
        """
        Check if we have sufficient permissions to access coredump data.

        Note: coredumpctl returns 1 when no dumps are found, which is a valid
        case that indicates we have proper permissions.
        """
        # Try without sudo first
        try:
            # Permission errors shouldn't return 1, while "no dumps found" does.
            # See https://github.com/systemd/systemd/blob/main/src/basic/errno-util.h
            guest.execute(ShellScript("coredumpctl info &>/dev/null || [ $? -eq 1 ]"), silent=True)
            logger.debug("Has permission to access coredump data")
            return True
        except tmt.utils.RunError:
            # If failed, try with sudo if the user is not already root
            if guest.facts.is_superuser is False:
                try:
                    guest.execute(
                        ShellScript("sudo coredumpctl info &>/dev/null || [ $? -eq 1 ]"),
                        silent=True,
                    )
                    logger.debug("Access to coredump data requires sudo, which is available")
                    return True
                except tmt.utils.RunError:
                    logger.debug("Cannot access coredump data even with sudo - permission issues")
                    return False
            else:
                logger.debug("Cannot access coredump data - permission issues")
                return False

    def _check_coredump_available(
        self, guest: "Guest", logger: tmt.log.Logger
    ) -> tuple[bool, str]:
        """
        Check if coredump functionality is available and usable.

        Checks for:
        1. systemd availability through guest facts
        2. coredumpctl command exists
        3. systemd-coredump.socket is active or can be activated
        4. Has sufficient permissions to access coredump data

        :returns: A tuple of (available, reason) where available is True if coredump
                 is available and usable, and reason is a string explaining why it's not
                 available if applicable.
        """
        # We need systemd for coredump functionality
        if not guest.facts.has_systemd:
            reason = "systemd not available"
            logger.debug(f"{reason}, skipping coredump check")
            return False, reason

        # Check for coredumpctl command
        if not self._has_coredumpctl(guest, logger):
            reason = "coredumpctl command not available"
            return False, reason

        # Check for systemd-coredump.socket
        if not self._has_active_socket(guest, logger):
            reason = "systemd-coredump.socket not active and could not be activated"
            return False, reason

        # Check for permissions
        if not self._has_required_permissions(guest, logger):
            reason = "insufficient permissions to access coredump data"
            return False, reason

        return True, ""

    def _wait_for_coredump_processes(self, guest: "Guest", logger: tmt.log.Logger) -> None:
        """
        Wait for systemd-coredump processes to finish processing dumps.

        Uses progressive waiting with a timeout to avoid getting stuck.
        """
        need_sudo = guest.facts.is_superuser is False
        sudo_prefix = "sudo " if need_sudo else ""

        total_wait = 0
        max_wait = 60  # Total maximum wait time in seconds
        wait_time = 1  # Start with 1 second, will increase progressively

        logger.debug("Checking if systemd-coredump processes are running")
        while total_wait < max_wait:
            try:
                # Check if any systemd-coredump processes are running
                cmd = f"{sudo_prefix}pgrep systemd-coredump || true"
                result = guest.execute(ShellScript(cmd), silent=True)

                # If no processes found, we're good to go
                if not result.stdout:
                    logger.debug("No systemd-coredump processes found")
                    return

                # If processes are still running, wait and try again
                process_count = len(result.stdout.splitlines())
                logger.debug(
                    f"Found {process_count} systemd-coredump processes, waiting {wait_time}s"
                )
                sleep(wait_time)

                # Increase wait time progressively (1, 2, 3, 4...)
                total_wait += wait_time
                wait_time = min(wait_time + 1, 5)  # Cap at 5 seconds per wait

            except tmt.utils.RunError:
                # If we can't check, just return
                logger.debug("Unable to check for systemd-coredump processes")
                return

        logger.debug(f"Timed out after {total_wait}s waiting for systemd-coredump processes")

    def _get_crashes(
        self,
        guest: "Guest",
        logger: tmt.log.Logger,
        check_files_path: Path,
        previous_dumps_file: Path,
    ) -> list[str]:
        """
        Get any new crashes that have been detected since the test started.

        Uses the timestamp of the latest coredump before the test to identify
        new coredumps created during test execution.
        """
        # Determine if we need sudo
        need_sudo = guest.facts.is_superuser is False
        sudo_prefix = "sudo " if need_sudo else ""

        # Make sure dumps are processed
        self._wait_for_coredump_processes(guest, logger)

        try:
            # Get the timestamp of the latest coredump before the test
            latest_timestamp = ""
            try:
                previous_output = guest.execute(Command("cat", previous_dumps_file)).stdout
                if previous_output:
                    # The output should contain just one line for the latest coredump
                    # Extract the timestamp (first two fields) if we have data
                    fields = previous_output.strip().split()
                    if len(fields) >= 2:
                        # Combine the date and time fields as the timestamp
                        latest_timestamp = f"{fields[0]} {fields[1]}"
                        logger.debug(
                            f"Latest coredump before test had timestamp: {latest_timestamp}"
                        )
            except tmt.utils.RunError:
                logger.debug("Unable to read previous dumps file, assuming no prior coredumps")

            # Get list of coredumps newer than the latest one before the test
            # Use --all to check coredumps from all users, not just current user
            if latest_timestamp:
                since_param = f'--since="{latest_timestamp}"'
                cmd = f"{sudo_prefix}coredumpctl list --all --no-legend --no-pager {since_param}"
                logger.debug(f"Checking for coredumps newer than: {latest_timestamp}")
            else:
                # If we have no prior timestamp, get all coredumps
                cmd = f"{sudo_prefix}coredumpctl list --all --no-legend --no-pager"
                logger.debug("No prior coredumps found, checking all available coredumps")

            output = guest.execute(ShellScript(cmd)).stdout

            if not output:
                return []

            # Process each crash entry
            crashes: list[str] = []
            for line in output.splitlines():
                fields = line.split()
                if len(fields) < 10:  # Ensure we have enough fields
                    logger.debug(f"Skipping malformed coredump line: {line}")
                    continue

                pid = fields[4]
                sig = fields[7]
                corefile = fields[8]
                exe = fields[9].replace("/", "_")

                # We're now using the timestamp to filter,
                # so all dumps in this list are already post-test

                # Get detailed info for this crash (use --all to ensure we can access it)
                cmd = f"{sudo_prefix}coredumpctl info --all --no-pager {pid}"
                crash_info = guest.execute(ShellScript(cmd)).stdout
                if not crash_info:
                    logger.debug(f"No crash info available for PID {pid}")
                    continue

                # Skip if this crash matches any ignore pattern
                if self.ignore_pattern:
                    matching_pattern = next(
                        (pattern for pattern in self.ignore_pattern if pattern.search(crash_info)),
                        None,
                    )
                    if matching_pattern:
                        logger.info(
                            f"Ignoring crash in PID {pid} ({exe}) due to pattern match: '{matching_pattern.pattern}'"  # noqa: E501
                        )
                        # Log full crash info at debug level
                        logger.debug(f"Full ignored crash info: {crash_info}")
                        continue

                # Save the crash info (with --all to ensure we can access it)
                info_filepath = check_files_path / f"dump.{exe}_{sig}_{pid}.txt"
                guest.execute(
                    ShellScript(
                        f"sh -c {sudo_prefix}coredumpctl info --all --no-pager {pid} > {info_filepath!s}"  # noqa: E501
                    )
                )
                logger.debug(f"Saved crash info to {info_filepath}")

                # Try to save the coredump if available
                if corefile not in ("none", "missing"):
                    dump_filename = f"dump.{exe}_{sig}_{pid}.core"
                    dump_path = check_files_path / dump_filename
                    try:
                        guest.execute(
                            ShellScript(
                                f"{sudo_prefix}coredumpctl dump --all --no-pager -o {dump_path!s} {pid}"  # noqa: E501
                            )
                        )
                        logger.debug(f"Saved coredump to {dump_path}")
                    except tmt.utils.RunError as exc:
                        logger.debug(f"Failed to save coredump for PID {pid}: {exc}")
                else:
                    logger.debug(f"Skipping dump for PID {pid}, corefile status: {corefile}")

                # This is a new, non-ignored crash
                crashes.append(crash_info)

            return crashes

        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to check for crashes: {exc}")
            return []

    def _check_coredump(
        self, invocation: "TestInvocation", logger: tmt.log.Logger
    ) -> tuple[ResultOutcome, list[Path]]:
        """
        Check coredump status and return appropriate result.

        :returns: A tuple of (outcome, log_files) where log_files is a list of
                 paths to files with coredump information and potential failures.
        """
        log_files: list[Path] = []

        # Check for crashes by comparing with the saved file of previous dumps
        crashes = self._get_crashes(
            invocation.guest,
            logger,
            invocation.check_files_path,
            self.coredump_last_dumps_filepath,
        )

        # Get list of generated files
        try:
            files_output = invocation.guest.execute(
                Command("find", invocation.check_files_path, "-type", "f")
            ).stdout

            if files_output:
                for file_path in files_output.splitlines():
                    path = Path(file_path)
                    if path.exists() and invocation.phase.step.workdir:
                        rel_path = path.relative_to(invocation.phase.step.workdir)
                        log_files.append(rel_path)
        except tmt.utils.RunError:
            logger.debug("Failed to list coredump files")

        log_files.append(save_failures(invocation, invocation.check_files_path, crashes))

        if crashes:
            return ResultOutcome.FAIL, log_files

        return ResultOutcome.PASS, log_files

    def _save_existing_coredumps(self, invocation: "TestInvocation") -> bool:
        """
        Save information about the latest coredump before the test.

        This allows us to only check for newer coredumps after the test.
        """
        self.coredump_last_dumps_filepath = (
            invocation.check_files_path / COREDUMP_LAST_DUMP_FILENAME
        )

        try:
            # Create directory for check files
            invocation.guest.execute(ShellScript(f"mkdir -p {invocation.check_files_path!s}"))

            # Determine if sudo is needed
            need_sudo = invocation.guest.facts.is_superuser is False
            sudo_prefix = "sudo " if need_sudo else ""

            # Get only the latest coredump before the test using -1 flag
            # and save it to a file. If there are no dumps, create an empty file.
            # Use --all to check coredumps from all users, not just current user
            invocation.guest.execute(
                ShellScript(
                    f"({sudo_prefix}coredumpctl list -1 --all --no-legend --no-pager || true) > "
                    f"{self.coredump_last_dumps_filepath!s}"
                )
            )
            return True
        except tmt.utils.RunError:
            return False


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
            ignore-pattern:
              - 'Process.*\\(sleep\\).*dumped core'  # Ignore sleep crashes
              - 'Package: ddcutil/2.1.2-2.fc41'      # Ignore dumps of a specific package

    The patterns are matched against the full coredumpctl info output, which includes
    fields like Process, Command Line, Signal, etc. You can use 'coredumpctl info'
    to see the available fields and their format.

    Common pattern examples:

    - Ignore all crashes from a specific process:
      `'Process.*\\(specific-process\\)'`

    - Ignore crashes with a specific signal:
      `'Signal: .*\\(SIGSEGV\\)'`

    - Ignore crashes from a specific package:
      `'Package: package-name/.*'`

    - Ignore crashes during a specific command:
      `'Command Line: .*specific-command-pattern.*'`

    .. versionadded:: 1.46
    """

    @staticmethod
    def _get_not_available_message(reason: Optional[str] = None) -> str:
        """Return a message explaining why coredump is not available."""
        if reason:
            base_message = f"Coredump detection was skipped: {reason}."
        else:
            base_message = (
                "Coredump detection was skipped because coredumpctl is not available or has "
                "insufficient privileges."
            )

        return (
            f"{base_message}\n\n"
            "The coredump check requires systemd-coredump to be installed and the "
            "systemd-coredump.socket to be active. Additionally, the user must have "
            "sufficient permissions to access coredump data."
        )

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

        available, reason = check._check_coredump_available(invocation.guest, logger)
        if not available:
            logger.debug(f"coredump not available: {reason}, skipping..")
            check.is_availability_reason = reason
            check.is_available = False
            # Use our temporary message until PR #3498 is merged
            return [
                CheckResult(
                    name="coredump",
                    result=ResultOutcome.SKIP,
                    note=[cls._get_not_available_message(reason)],
                )
            ]

        # Initialize outcome to ERROR in case we can't save the current coredumps list
        outcome = ResultOutcome.ERROR
        log_files: list[Path] = []

        if check._save_existing_coredumps(invocation):
            check._configure_coredump(invocation.guest, logger)
            outcome, log_files = check._check_coredump(invocation, logger)

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
        if not check.is_available:
            return [
                CheckResult(
                    name="coredump",
                    result=ResultOutcome.SKIP,
                    note=[cls._get_not_available_message(check.is_availability_reason)],
                )
            ]

        if not invocation.is_guest_healthy:
            return [
                CheckResult(
                    name="coredump",
                    result=ResultOutcome.SKIP,
                    note=["Coredump check skipped because the guest is not healthy."],
                )
            ]

        outcome, log_files = check._check_coredump(invocation, logger)
        return [CheckResult(name="coredump", result=outcome, log=log_files)]
