"""
Prepare plugin to verify installed packages came from expected repositories.
"""

from typing import Any, Optional, cast

import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.log import Logger
from tmt.steps import PluginOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.utils import Environment, ShellScript


def _parse_verify_string(value: str) -> dict[str, str]:
    """Parse 'package=name,expected_repo=repo' format into dict."""
    result: dict[str, str] = {}
    for part in value.split(','):
        if '=' not in part:
            raise tmt.utils.SpecificationError(
                f"Invalid verify format '{value}': expected 'key=value,key2=value2'"
            )
        key, val = part.split('=', 1)
        result[key.strip()] = val.strip()
    return result


def _normalize_verify_mappings(
    key_address: str,
    value: Any,
    logger: Logger,
) -> list[dict[str, str]]:
    """
    Normalize verify mappings from list of dicts or strings.

    Accepts:
    - None -> empty list
    - Single dict -> list with one dict
    - List of dicts -> list of dicts
    - String (CLI format: 'package=name,expected_repo=repo') -> list with one dict
    - List of strings -> list of dicts
    """
    if value is None:
        return []

    # Handle string input from CLI
    if isinstance(value, str):
        return [_parse_verify_string(value)]

    if isinstance(value, dict):
        # Single mapping from YAML
        if 'package' not in value or 'expected_repo' not in value:
            raise tmt.utils.SpecificationError(
                f"Invalid verify mapping at '{key_address}': "
                "must contain 'package' and 'expected_repo' keys."
            )
        return [value]

    if isinstance(value, (list, tuple)):
        # List of mappings
        result: list[dict[str, str]] = []
        for i, item in enumerate(cast(list[Any], value)):
            if isinstance(item, str):
                # CLI format string in list
                result.append(_parse_verify_string(item))
            elif isinstance(item, dict):
                # YAML dict format
                if 'package' not in item or 'expected_repo' not in item:
                    raise tmt.utils.SpecificationError(
                        f"Invalid verify mapping at '{key_address}[{i}]': "
                        "must contain 'package' and 'expected_repo' keys."
                    )
                result.append(cast(dict[str, str], item))
            else:
                raise tmt.utils.SpecificationError(
                    f"Invalid verify mapping at '{key_address}[{i}]': "
                    f"expected dict or string, got {type(item).__name__}."
                )
        return result

    raise tmt.utils.NormalizationError(
        key_address, value, 'a dict, string, or list of dicts/strings'
    )


@container
class PrepareVerifyInstallationData(PrepareStepData):
    """Data class for verify-installation prepare plugin."""

    verify: list[dict[str, str]] = field(
        default_factory=list,
        option='--verify',
        metavar='MAPPING',
        multiple=True,
        help="Package and expected repository mapping (format: package=name,expected_repo=repo).",
        normalize=_normalize_verify_mappings,
    )


@tmt.steps.provides_method('verify-installation')
class PrepareVerifyInstallation(PreparePlugin[PrepareVerifyInstallationData]):
    """
    Verify installed packages came from expected repositories.

    This plugin checks that installed packages were actually installed
    from the expected repositories. It runs after package installation
    to verify the ground truth of where packages came from.

    Example usage:

    .. code-block:: yaml

        prepare:
            how: verify-installation
            order: 76
            verify:
                - package: mypackage
                  expected_repo: tmt-artifact-shared
                - package: otherpkg
                  expected_repo: tmt-artifact-shared
    """

    _data_class = PrepareVerifyInstallationData
    DEFAULT_ORDER = 76

    def go(
        self,
        *,
        guest: Guest,
        environment: Optional[Environment] = None,
        logger: Logger,
    ) -> PluginOutcome:
        """Perform package source verification."""
        outcome = super().go(guest=guest, environment=environment, logger=logger)

        if self.is_dry_run:
            return outcome

        if not self.data.verify:
            logger.verbose("No packages to verify.", level=2)
            return outcome

        logger.info(
            f"Verifying {len(self.data.verify)} package(s) came from expected repositories.",
            color='green',
        )

        failures = self._verify_packages(guest, self.data.verify, logger)

        if failures:
            self._report_failures(failures)
            raise tmt.utils.PrepareError(
                f"Package source verification failed for {len(failures)} package(s)."
            )

        logger.info("All packages verified successfully.", color='green')
        return outcome

    def _verify_packages(
        self,
        guest: Guest,
        mappings: list[dict[str, str]],
        logger: Logger,
    ) -> list['VerificationFailure']:
        """Verify all packages came from expected repositories."""
        failures: list[VerificationFailure] = []

        for mapping in mappings:
            package = mapping['package']
            expected_repo = mapping['expected_repo']
            actual_repo = self._get_package_repository(guest, package, logger)

            if actual_repo is None:
                failures.append(
                    VerificationFailure(
                        package=package,
                        expected_repo=expected_repo,
                        actual_repo=None,
                        reason="Package not installed or not found",
                    )
                )
                continue

            if not self._repo_matches(expected_repo, actual_repo):
                failures.append(
                    VerificationFailure(
                        package=package,
                        expected_repo=expected_repo,
                        actual_repo=actual_repo,
                        reason=(
                            f"Package installed from '{actual_repo}', expected '{expected_repo}'"
                        ),
                    )
                )

        return failures

    def _get_package_repository(
        self,
        guest: Guest,
        package: str,
        logger: Logger,
    ) -> Optional[str]:
        """Query which repository a package was installed from."""
        package_manager = guest.facts.package_manager

        if package_manager in ('dnf', 'dnf5', 'yum'):
            return self._get_repo_dnf(guest, package, logger)

        logger.warning(f"Package source verification not supported for {package_manager}")
        return None

    def _get_repo_dnf(
        self,
        guest: Guest,
        package: str,
        logger: Logger,
    ) -> Optional[str]:
        """
        Get repository for package using dnf.

        Uses: dnf info --installed <package> to get repository info
        """
        import shlex

        # First check if package is installed using rpm
        try:
            output = guest.execute(
                ShellScript(f'rpm -q {shlex.quote(package)}'),
                silent=True,
            )
            if not output.stdout:
                return None
            # Package is installed, get the exact nevra
            installed_nevra = output.stdout.strip().split('\n')[0]
            logger.debug(f"Found installed package: {installed_nevra}")
        except tmt.utils.RunError:
            # Package not installed
            logger.debug(f"Package '{package}' not found via rpm -q")
            return None

        # Get repository info from dnf
        try:
            dnf_output = guest.execute(
                ShellScript(f'dnf info --installed {shlex.quote(package)}'),
                silent=True,
            )

            if dnf_output.stdout:
                repo = self._parse_dnf_info_repo(dnf_output.stdout)
                if repo:
                    logger.debug(f"Package '{package}' installed from repo: {repo}")
                    return repo

            logger.debug(f"Could not parse repository from dnf info for '{package}'")
            return None
        except tmt.utils.RunError as e:
            logger.debug(f"dnf info failed for '{package}': {e}")
            return None

    def _parse_dnf_info_repo(self, dnf_output: str) -> Optional[str]:
        """Parse 'Repository' or 'From repo' line from dnf info output."""
        for line in dnf_output.split('\n'):
            # Check for Repository line first
            if line.startswith('Repository'):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    return parts[1].strip()
            # Also check for From repo line (dnf5 format)
            if 'From repo' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    return parts[1].strip()
        return None

    def _repo_matches(self, expected: str, actual: str) -> bool:
        """Check if actual repository matches expected."""
        if expected == actual:
            return True
        if expected in actual:
            return True
        return False

    def _report_failures(self, failures: list['VerificationFailure']) -> None:
        """Report verification failures to user."""
        self.info('')
        self.info('Package source verification failed:', color='red', shift=1)

        for failure in failures:
            self.info('')
            self.info(failure.package, color='red', shift=2)
            self.info(f"Expected: '{failure.expected_repo}'", shift=3)
            self.info(f"Actual:   '{failure.actual_repo or 'NOT INSTALLED'}'", shift=3)
            if failure.reason:
                self.info(f"Reason:   {failure.reason}", shift=3)

        self.info('')
        self.info(
            "Packages must be installed from the expected repositories.",
            color='yellow',
            shift=1,
        )


@container(frozen=True)
class VerificationFailure:
    """Record of a verification failure."""

    package: str
    expected_repo: str
    actual_repo: Optional[str]
    reason: str
