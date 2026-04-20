from typing import Optional

import fmf.utils

import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.log import Logger
from tmt.package_managers import SpecialPackageOrigin
from tmt.result import PhaseResult, ResultGuestData, ResultOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.utils import Environment


@container
class PrepareVerifyInstallationData(PrepareStepData):
    order: int = field(
        default=tmt.steps.PHASE_ORDER_PREPARE_VERIFY_INSTALLATION,
        help='Order in which the phase should be handled.',
    )

    verify: dict[str, list[str]] = field(
        default_factory=dict,
        help="""
            Mapping of package names to expected source repository names.
            A package passes verification if it is installed and it was
            installed from one of the listed repositories. A single string
            value is accepted and treated as a one-element list.
            """,
        normalize=tmt.utils.normalize_string_list_dict,
    )


@tmt.steps.provides_method('verify-installation')
class PrepareVerifyInstallation(PreparePlugin[PrepareVerifyInstallationData]):
    """
    Verify that installed packages came from expected repositories.

    Currently only supports DNF-based package managers (``dnf``,
    ``dnf5``). Other package managers will cause the step to fail with
    an unsupported error.

    Packages pre-installed in a container image (or otherwise not installed
    via a repository) report an unknown source. Such packages are attributed
    to ``<unknown>`` and can be matched by specifying ``'<unknown>'`` as the
    expected repository in the verification mapping.

    Verification failures are recorded as ``FAIL`` results in the
    prepare phase output and cause the prepare step to fail, preventing
    test execution.

    Each package may specify a single expected repository (string) or a list
    of acceptable repositories. A package passes if its actual source matches
    any of the listed repos.

    Example usage:

    .. code-block:: yaml

        prepare:
            how: verify-installation
            verify:
                make: tmt-artifact-shared
                gcc: fedora
                curl:
                  - tmt-artifact-shared
                  - updates
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
            self.verbose('No packages to verify.')
            return outcome

        self.info(
            fmf.utils.listed(list(self.data.verify.keys()), 'package'),
            color='green',
        )

        # Resolve capabilities (paths, virtual provides) to actual package names via
        # rpm --whatprovides. Unresolvable entries keep their original string so they
        # surface as NOT_INSTALLED in the origin check below.
        try:
            capability_mapping = guest.package_manager.resolve_capabilities(
                self.data.verify.keys()
            )
        except NotImplementedError:
            capability_mapping = {}
        verify = {
            (capability_mapping.get(capability) or capability): repos
            for capability, repos in self.data.verify.items()
        }

        try:
            package_origins = guest.package_manager.get_package_origin(verify.keys())
        except (NotImplementedError, tmt.utils.GeneralError) as err:
            error: Exception = (
                tmt.utils.PrepareError(
                    f"Package source verification not supported for "
                    f"'{guest.facts.package_manager}' package manager."
                )
                if isinstance(err, NotImplementedError)
                else err
            )
            outcome.results.append(
                PhaseResult(
                    name=self.name,
                    result=ResultOutcome.ERROR,
                    note=tmt.utils.render_exception_as_notes(error),
                    guest=ResultGuestData.from_guest(guest=guest),
                )
            )
            outcome.exceptions.append(error)
            return outcome

        failed_packages: list[str] = []
        for package, expected_repos in verify.items():
            actual_origin = package_origins[package]

            if actual_origin in expected_repos:
                outcome.results.append(
                    PhaseResult(
                        name=f'{self.name} / {package}',
                        result=ResultOutcome.PASS,
                        note=[
                            f"Package '{package}' installed from expected repo '{actual_origin}'."
                        ],
                        guest=ResultGuestData.from_guest(guest=guest),
                    )
                )
                continue

            failed_packages.append(package)
            expected_repos_formatted = fmf.utils.listed(expected_repos, quote="'", join='or')
            if actual_origin is SpecialPackageOrigin.NOT_INSTALLED:
                note = (
                    f"Package '{package}': expected repo {expected_repos_formatted},"
                    f" but the package is not installed."
                )
            else:
                note = (
                    f"Package '{package}': expected repo {expected_repos_formatted},"
                    f" actual '{actual_origin}'."
                )

            outcome.results.append(
                PhaseResult(
                    name=f'{self.name} / {package}',
                    result=ResultOutcome.FAIL,
                    note=[note],
                    guest=ResultGuestData.from_guest(guest=guest),
                )
            )

        if failed_packages:
            self.info(f"Package source verification failed for: {', '.join(failed_packages)}")
        else:
            self.info('All packages verified successfully.', color='green')

        return outcome
