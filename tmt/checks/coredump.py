import dataclasses
import re
from re import Pattern
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckEvent, CheckPlugin, _RawCheck, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import Command, field

if TYPE_CHECKING:
    import tmt.base
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest

DEFAULT_TMP_PATH = "/var/tmp/tmt"  # noqa: S108


@dataclasses.dataclass
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

    def _configure_coredump(
            self, guest: "Guest", logger: tmt.log.Logger, check_files_path: str
            ) -> bool:
        """Configure coredump storage."""
        try:
            # This should be default anyway
            config = """[Coredump]
Storage=external
Compress=yes
ProcessSizeMax=32G
ExternalSizeMax=32G
JournalSizeMax=767M
MaxUse=0
KeepFree=0
"""
            guest.execute(
                Command(
                    "sh",
                    "-c",
                    f"mkdir -p /etc/systemd/coredump.conf.d && "
                    f"echo '{config}' > /etc/systemd/coredump.conf.d/50-tmt.conf",
                    )
                )

            # TODO: check if we need non-default config here
            # Configure kernel core pattern to use systemd-coredump
            # guest.execute(
            #    Command(
            #        "sh",
            #        "-c",
            #        "echo '|/usr/lib/systemd/systemd-coredump %P %u %g %s %t %c %h' > /proc/sys/kernel/core_pattern"  # noqa: E501
            #    )
            # )

            return True

        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to configure coredump: {exc}")
            return False

    def _ensure_coredump_running(
            self, guest: "Guest", logger: tmt.log.Logger, check_files_path: str
            ) -> bool:
        """Ensure coredump is configured."""
        try:
            if not self._configure_coredump(guest, logger, check_files_path):
                return False

            return True

        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to configure coredump: {exc}")
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
                if self.ignore_patterns:
                    ignored = False
                    for pattern in self.ignore_patterns:
                        if pattern.search(crash_info):
                            logger.debug(
                                f"Ignoring crash due to pattern '{pattern.pattern}': {crash_info}"
                                )
                            ignored = True
                            break
                    if ignored:
                        continue

                # Save the crash info
                info_file = f"{check_files_path}/dump.{exe}_{sig}_{pid}.txt"
                guest.execute(
                    Command("sh", "-c", f"coredumpctl info --no-pager {pid} > {info_file}")
                    )
                logger.debug(f"Saved crash info to {info_file}")

                # Try to save the coredump if available
                if corefile not in ("none", "missing"):
                    dump_file = f"{check_files_path}/dump.{exe}_{sig}_{pid}.core"
                    try:
                        guest.execute(
                            Command("coredumpctl", "dump", "--no-pager", "-o", dump_file, pid)
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
            ) -> ResultOutcome:
        """Check coredump status and return appropriate result."""
        # Only configure coredump in before_test
        if event == CheckEvent.BEFORE_TEST:
            if not self._ensure_coredump_running(
                    invocation.guest, logger, str(invocation.check_files_path)
                    ):
                return ResultOutcome.ERROR

            # Store current time for --since filtering
            invocation.guest.execute(
                Command(
                    "sh",
                    "-c",
                    f"date '+%Y-%m-%d %H:%M:%S' > {DEFAULT_TMP_PATH}/coredump-timestamp",
                    )
                )
            return ResultOutcome.PASS

        # Check for crash reports in after_test
        output = invocation.guest.execute(
            Command("cat", f"{DEFAULT_TMP_PATH}/coredump-timestamp")
            ).stdout

        if not output:
            logger.debug("Failed to read timestamp file")
            return ResultOutcome.ERROR

        start_time = output.strip()

        if self._check_for_crashes(
                invocation.guest, logger, str(invocation.check_files_path), start_time
                ):
            return ResultOutcome.FAIL

        return ResultOutcome.PASS


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
    def essential_requires(
            cls, guest: "Guest", test: "tmt.base.Test", logger: tmt.log.Logger
            ) -> list["tmt.base.DependencySimple"]:
        # Avoid circular imports
        import tmt.base

        # Required packages for coredump functionality
        return [tmt.base.DependencySimple("systemd-udev")]  # includes coredumpctl

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
        outcome = check._check_coredump(invocation, CheckEvent.BEFORE_TEST, logger)
        return [CheckResult(name="coredump", result=outcome)]

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

        outcome = check._check_coredump(invocation, CheckEvent.AFTER_TEST, logger)
        return [CheckResult(name="coredump", result=outcome)]
