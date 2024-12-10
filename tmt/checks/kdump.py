import dataclasses
import re
from re import Pattern
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt._compat.pathlib import Path
from tmt.checks import Check, CheckEvent, CheckPlugin, _RawCheck, provides_check
from tmt.result import ResultOutcome
from tmt.utils import Command, field

if TYPE_CHECKING:
    import tmt.base
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest

DEFAULT_TMP_PATH = "/var/tmp/tmt"  # noqa: S108


@dataclasses.dataclass
class KdumpCheck(Check):
    """Base configuration for kdump checks."""

    def _configure_kdump_service(self, guest: "Guest", logger: tmt.log.Logger) -> bool:
        """Configure and enable kdump service."""
        try:
            # Setup kernel options for kdump
            try:
                # Try reset-crashkernel first (works on newer systems)
                guest.execute(Command("kdumpctl", "reset-crashkernel"))
            except tmt.utils.RunError as exc:
                logger.debug(f"Failed to set kernel options for kdump: {exc}")

                # On el8, we need to use grubby with recommended value
                try:
                    # Get recommended crashkernel value
                    output = guest.execute(Command("kdumpctl", "estimate")).stdout
                    if not output:
                        logger.debug("Failed to get recommended crashkernel value")
                        return False

                    # Extract recommended value
                    for line in output.splitlines():
                        if "Recommended" in line:
                            crashkernel = line.split()[2]
                            break
                    else:
                        logger.debug("Could not find recommended crashkernel value")
                        return False

                    # Update kernel args with recommended value
                    guest.execute(
                        Command(
                            "grubby", "--args=crashkernel=" + crashkernel, "--update-kernel=ALL"
                            )
                        )
                    logger.debug(f"Set crashkernel={crashkernel} using grubby")

                except tmt.utils.RunError as exc:
                    logger.debug(f"Failed to set crashkernel using grubby: {exc}")
                    return False

            # Enable kdump service
            try:
                guest.execute(Command("systemctl", "enable", "kdump.service"))
            except tmt.utils.RunError as exc:
                logger.debug(f"Failed to enable kdump service: {exc}")
                return False

            # Reboot to apply changes
            try:
                guest.reboot()
            except tmt.utils.RunError as exc:
                logger.debug(f"Failed to reboot after kdump configuration: {exc}")
                return False

            return True

        except Exception as exc:
            logger.debug(f"Unexpected error configuring kdump: {exc}")
            return False

    def _check_kdump_status(self, guest: "Guest", logger: tmt.log.Logger,
                            previous_vmcore_time: Optional[str] = None) -> bool:
        """Check kdump status and last vmcore time."""
        try:
            output = guest.execute(Command("kdumpctl", "status")).stdout
            if not output:
                logger.debug("Failed to get kdump status")
                return False

            # Check if kdump is operational
            if "Kdump is operational" not in output:
                logger.debug("Kdump is not operational")
                return False

            # Check last vmcore time if provided
            if previous_vmcore_time:
                for line in output.splitlines():
                    if "Last successful vmcore creation" in line:
                        current_time = line.split("on ", 1)[1].strip()
                        if current_time != previous_vmcore_time:
                            logger.debug(f"New vmcore detected: {current_time}")
                            return False

            return True

        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to check kdump status: {exc}")
            return False


@dataclasses.dataclass
class DefaultKdumpCheck(KdumpCheck):
    """Configuration for default kdump check."""

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

    def _configure_local_kdump(
            self, guest: "Guest", logger: tmt.log.Logger, check_files_path: str
            ) -> bool:
        """Configure local kdump storage."""
        try:
            # Update kdump.conf to use check_files_path
            guest.execute(
                Command("sed", "-i", f"s|^path.*|path {check_files_path}|", "/etc/kdump.conf")
                )
            return True

        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to configure kdump storage: {exc}")
            return False

    def _check_for_crashes(
            self, guest: "Guest", logger: tmt.log.Logger, check_files_path: str
            ) -> bool:
        """Check if any crashes have been detected."""
        try:
            # Look for vmcore files
            output = guest.execute(Command("find", check_files_path, "-name", "vmcore")).stdout

            if not output:
                return False

            # Process each vmcore
            has_crashes = False
            for vmcore in output.splitlines():
                vmcore_path = Path(vmcore)
                dmesg_path = vmcore_path.parent / "vmcore-dmesg.txt"

                # Skip if this crash matches any ignore pattern
                if self.ignore_patterns:
                    try:
                        # Check patterns on guest side
                        patterns = "|".join(p.pattern for p in self.ignore_patterns)
                        guest.execute(Command("sh", "-c", f"grep -E '{patterns}' {dmesg_path}"))
                        logger.debug(f"Ignoring crash due to pattern match: {vmcore}")
                        continue
                    except tmt.utils.RunError:
                        # No pattern match, treat as crash
                        pass

                # This is a non-ignored crash
                has_crashes = True
                logger.debug(f"Found vmcore: {vmcore}")

            return has_crashes

        except tmt.utils.RunError as exc:
            logger.debug(f"Failed to check for crashes: {exc}")
            return False

    def _check_kdump(
            self, invocation: "TestInvocation", event: CheckEvent, logger: tmt.log.Logger
            ) -> ResultOutcome:
        """Check kdump status and return appropriate result."""
        # Configure kdump in before_test
        if event == CheckEvent.BEFORE_TEST:
            if not self._configure_kdump_service(invocation.guest, logger):
                return ResultOutcome.ERROR

            if not self._configure_local_kdump(
                    invocation.guest, logger, str(invocation.check_files_path)
                    ):
                return ResultOutcome.ERROR

            return ResultOutcome.PASS

        # Check for crash reports in after_test
        if self._check_for_crashes(invocation.guest, logger, str(invocation.check_files_path)):
            return ResultOutcome.FAIL

        return ResultOutcome.PASS


@dataclasses.dataclass
class CustomKdumpCheck(KdumpCheck):
    """Configuration for custom kdump check."""

    # Commands to run for configuration
    setup_commands: list[str] = field(
        default_factory=list,
        help="""
             List of commands to run for kdump configuration. These commands will be
             executed before enabling the kdump service and rebooting. The commands
             are responsible for setting up the kdump configuration as needed.
             """,
        )

    def _check_kdump(
            self, invocation: "TestInvocation", event: CheckEvent, logger: tmt.log.Logger
            ) -> ResultOutcome:
        """Check kdump status and return appropriate result."""
        # Configure kdump in before_test
        if event == CheckEvent.BEFORE_TEST:
            # Get initial vmcore time if available
            try:
                output = invocation.guest.execute(Command("kdumpctl", "status")).stdout
                if output:
                    for line in output.splitlines():
                        if "Last successful vmcore creation" in line:
                            # Store timestamp in guest file
                            timestamp = line.split("on ", 1)[1].strip()
                            invocation.guest.execute(
                                Command(
                                    "sh",
                                    "-c",
                                    f"echo '{timestamp}' > {DEFAULT_TMP_PATH}/kdump-timestamp",
                                    )
                                )
                            break
            except tmt.utils.RunError:
                pass

            # Run setup commands
            for cmd in self.setup_commands:
                try:
                    invocation.guest.execute(Command("sh", "-c", cmd))
                except tmt.utils.RunError as exc:
                    logger.debug(f"Failed to run setup command '{cmd}': {exc}")
                    return ResultOutcome.ERROR

            # Configure kdump service
            if not self._configure_kdump_service(invocation.guest, logger):
                return ResultOutcome.ERROR

            return ResultOutcome.PASS

        # Check kdump status in after_test
        try:
            # Get previous timestamp if it exists
            output = invocation.guest.execute(
                Command("cat", f"{DEFAULT_TMP_PATH}/kdump-timestamp")
                ).stdout
            previous_time = output.strip() if output else None

            if not self._check_kdump_status(invocation.guest, logger, previous_time):
                return ResultOutcome.FAIL

        except tmt.utils.RunError:
            # No previous timestamp, just check operational status
            if not self._check_kdump_status(invocation.guest, logger):
                return ResultOutcome.FAIL

        return ResultOutcome.PASS


@provides_check("kdump")
class DefaultKdump(CheckPlugin[DefaultKdumpCheck]):
    """
    Check for kernel crashes using kdump.

    The check monitors for kernel crashes by configuring kdump to save vmcore files
    to the test's check files directory. By default, any crash will cause the test
    to fail.

    Example config with optional ignore patterns:

    .. code-block:: yaml

        check:
          - how: kdump
            ignore-patterns:
              - 'kernel panic on CPU.*'  # Ignore specific kernel panics
              - 'BUG: soft lockup.*'     # Ignore soft lockups

    The patterns are matched against the vmcore-dmesg.txt content. You can examine
    these files in the test's check files directory after a crash.

    .. versionadded:: 1.41
    """

    _check_class = DefaultKdumpCheck

    @classmethod
    def essential_requires(
            cls, guest: "Guest", test: "tmt.base.Test", logger: tmt.log.Logger
            ) -> list["tmt.base.DependencySimple"]:
        # Avoid circular imports
        import tmt.base

        # Required packages for kdump functionality
        return [tmt.base.DependencySimple("kexec-tools"), tmt.base.DependencySimple("crash")]


@provides_check("kdump-custom")
class CustomKdump(CheckPlugin[CustomKdumpCheck]):
    """
    Check for kernel crashes using custom kdump configuration.

    The check allows users to provide their own kdump configuration commands.
    These commands will be executed before enabling the kdump service and
    rebooting. Any vmcore creation during the test will cause a failure.

    Example config with custom setup:

    .. code-block:: yaml

        check:
          - how: kdump-custom
            setup-commands:
              - echo "path /custom/path" > /etc/kdump.conf
              - echo "core_collector makedumpfile -l --message-level 1 -d 31" >> /etc/kdump.conf

    .. versionadded:: 1.41
    """

    _check_class = CustomKdumpCheck

    @classmethod
    def essential_requires(
            cls, guest: "Guest", test: "tmt.base.Test", logger: tmt.log.Logger
            ) -> list["tmt.base.DependencySimple"]:
        # Avoid circular imports
        import tmt.base

        # Required packages for kdump functionality
        return [tmt.base.DependencySimple("kexec-tools"), tmt.base.DependencySimple("crash")]
