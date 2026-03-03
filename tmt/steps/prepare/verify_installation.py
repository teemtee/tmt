from typing import Any, Optional, cast

import fmf.utils

import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.log import Logger
from tmt.package_managers import Package
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.utils import Environment


@container
class VerifyMapping:
    """A single package-to-repository verification mapping."""

    package: Package
    expected_repo: str


@container
class VerificationFailure:
    """Record of a verification failure."""

    package: str
    expected_repo: str
    actual_repo: Optional[str] = None


def _parse_verify_string(key_address: str, value: str) -> VerifyMapping:
    """Parse 'package,repo' format into a VerifyMapping."""
    parts = value.split(',')
    if len(parts) != 2:
        raise tmt.utils.NormalizationError(
            key_address, value, "a 'package_name,repository_name' string"
        )
    return VerifyMapping(package=Package(parts[0].strip()), expected_repo=parts[1].strip())


def _normalize_verify_mappings(
    key_address: str,
    value: Any,
    logger: Logger,
) -> list[VerifyMapping]:
    """Normalize verify mappings from a string or list of 'package,repo' strings."""
    return [
        _parse_verify_string(key_address, s)
        for s in tmt.utils.normalize_string_list(key_address, value, logger)
    ]


@container
class PrepareVerifyInstallationData(PrepareStepData):
    """Data class for verify-installation prepare plugin."""

    order: int = field(
        default=tmt.steps.PHASE_ORDER_PREPARE_VERIFY_INSTALLATION,
        help='Order in which the phase should be handled.',
    )

    verify: list[VerifyMapping] = field(
        default_factory=list,
        option='--verify',
        metavar='MAPPING',
        multiple=True,
        help="Package and expected repository mapping (format: package_name,repository_name).",
        normalize=_normalize_verify_mappings,
        serialize=lambda mappings: [f'{m.package},{m.expected_repo}' for m in mappings],
        unserialize=lambda data: [
            _parse_verify_string('verify', item) for item in cast(list[str], data)
        ],
    )


@tmt.steps.provides_method('verify-installation')
class PrepareVerifyInstallation(PreparePlugin[PrepareVerifyInstallationData]):
    """
    Verify that installed packages came from expected repositories.

    This plugin checks that installed packages were actually installed
    from the expected repositories. It runs after package installation
    to verify the ground truth of where packages came from.

    .. note::

        Currently only supports DNF-based package managers (dnf, dnf5, yum).
        Other package managers will log a warning and skip verification.

    .. warning::

        Verification failure will cause the prepare step to fail and
        prevent test execution.

    Example usage:

    .. code-block:: yaml

        prepare:
            how: verify-installation
            verify:
                - make,fedora
                - gcc,fedora

    .. code-block:: shell

        prepare --how verify-installation --verify make,fedora --verify gcc,fedora
    """

    _data_class = PrepareVerifyInstallationData

    def go(
        self,
        *,
        guest: Guest,
        environment: Optional[Environment] = None,
        logger: Logger,
    ) -> tmt.steps.PluginOutcome:
        """Perform package source verification."""
        outcome = super().go(guest=guest, environment=environment, logger=logger)

        if self.is_dry_run:
            return outcome

        if not self.data.verify:
            self.verbose('verify', 'no packages to verify', level=2)
            return outcome

        # Probe capability without executing a remote command — engine methods
        # only build a ShellScript locally, so this raises NotImplementedError
        # immediately if the package manager doesn't support repo queries.
        try:
            guest.package_manager.engine.get_installed_repo('')
        except NotImplementedError:
            self.warn(
                f"Package source verification not supported for "
                f"'{guest.facts.package_manager}' package manager, skipping."
            )
            return outcome

        self.info(
            'verify',
            fmf.utils.listed([m.package for m in self.data.verify], 'package'),
            'green',
        )

        failures = self._verify_packages(guest, self.data.verify)

        if failures:
            self._report_failures(failures)
            raise tmt.utils.PrepareError(
                f"Package source verification failed for {len(failures)} package(s)."
            )

        self.info('verify', 'all packages verified successfully', 'green')

        return outcome

    def _verify_packages(
        self,
        guest: Guest,
        verify_mappings: list[VerifyMapping],
    ) -> list[VerificationFailure]:
        """Verify all packages came from expected repositories."""
        failures: list[VerificationFailure] = []

        for verify_mapping in verify_mappings:
            actual_repo = self._get_package_repository(guest, verify_mapping.package)

            if actual_repo != verify_mapping.expected_repo:
                failures.append(
                    VerificationFailure(
                        package=verify_mapping.package,
                        expected_repo=verify_mapping.expected_repo,
                        actual_repo=actual_repo,
                    )
                )

        return failures

    def _get_package_repository(
        self,
        guest: Guest,
        package: str,
    ) -> Optional[str]:
        """Query which repository a package was installed from."""
        try:
            repo = guest.package_manager.get_installed_repo(package)
        except tmt.utils.RunError as e:
            self.debug(f"Package repository query failed for '{package}': {e}")
            return None

        if repo:
            self.debug(f"Package '{package}' installed from repo: {repo}")
        else:
            self.debug(f"Could not determine repository for '{package}'")
        return repo

    def _report_failures(self, failures: list[VerificationFailure]) -> None:
        """Report verification failures to user."""
        for failure in failures:
            if failure.actual_repo is None:
                self.warn(
                    f"Package '{failure.package}': expected repo '{failure.expected_repo}'"
                    f", but package is not installed, its source repo cannot be determined,"
                )
            else:
                self.warn(
                    f"Package '{failure.package}': expected repo '{failure.expected_repo}'"
                    f", actual '{failure.actual_repo}'."
                )
