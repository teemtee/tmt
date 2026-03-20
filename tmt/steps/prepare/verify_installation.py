from typing import Optional

import fmf.utils

import tmt.base.core
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

    verify: dict[str, str] = field(
        default_factory=dict,
        help="Mapping of package names to expected source repository names.",
        normalize=tmt.utils.normalize_string_dict,
    )

    auto: bool = field(
        default=False,
        option='--auto/--no-auto',
        is_flag=True,
        help="""
            Automatically verify packages listed in ``require`` or ``recommend``
            that are present in the artifact metadata (``artifacts.yaml``) were
            installed from the artifact repository. Entries in ``verify`` take
            precedence over auto-detected ones.
            """,
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
    to ``<unknown>`` and can be matched with ``expected-repo: '<unknown>'``
    in the verification mapping.

    Verification failures are recorded as ``FAIL`` results in the
    prepare phase output and cause the prepare step to fail, preventing
    test execution.

    Example usage:

    .. code-block:: yaml

        prepare:
            how: verify-installation
            verify:
                make: tmt-artifact-shared
                gcc: fedora
    """

    _data_class = PrepareVerifyInstallationData

    def _build_auto_verify(self, guest: Guest) -> dict[str, str]:
        """
        Build a verify mapping from artifact metadata and test requirements.

        Reads ``artifacts.yaml`` from the plan workdir, collects all
        package names provided by artifact providers, and intersects them
        with packages listed in ``require``/``recommend`` of tests enabled
        on this guest.  Returns a mapping of intersecting package names to
        the artifact shared repository name.
        """
        from tmt.steps.prepare.artifact import (
            ARTIFACT_METADATA_FILENAME,
            ARTIFACT_SHARED_REPO_NAME,
        )

        artifacts_file = self.plan_workdir / ARTIFACT_METADATA_FILENAME

        if not artifacts_file.exists():
            self.debug('No artifacts.yaml found, skipping auto-verification.')
            return {}

        try:
            metadata = tmt.utils.yaml_to_dict(artifacts_file.read_text())
        except tmt.utils.GeneralError as err:
            self.warn(f"Failed to read artifacts.yaml: {err}")
            return {}

        # Collect all package names provided by artifact providers.
        artifact_package_names: set[str] = {
            artifact['version']['name']
            for provider in metadata.get('providers', [])
            for artifact in provider.get('artifacts', [])
        }

        if not artifact_package_names:
            self.debug('No artifact packages found in artifacts.yaml.')
            return {}

        # Collect require/recommend package names for tests enabled on this guest.
        # Only DependencySimple entries are package names; fmf/file deps are skipped.
        require_recommend_names: set[str] = set()
        for test_origin in self.step.plan.discover.tests(enabled=True):
            test = test_origin.test
            if not test.enabled_on_guest(guest):
                continue
            for dep in (*test.require, *test.recommend):
                if isinstance(dep, tmt.base.core.DependencySimple):
                    require_recommend_names.add(str(dep))

        intersection = artifact_package_names & require_recommend_names
        if not intersection:
            self.debug('No overlap between artifact packages and test requirements.')
            return {}

        self.debug(
            f"Auto-verifying {fmf.utils.listed(sorted(intersection), 'package')} "
            f"against '{ARTIFACT_SHARED_REPO_NAME}'."
        )

        unverified = require_recommend_names - artifact_package_names
        if unverified:
            self.warn(
                f"{fmf.utils.listed(sorted(unverified), 'package')} "
                f"from require/recommend not found in artifacts.yaml, "
                f"consider adding a custom verify-installation entry: "
                f"{', '.join(sorted(unverified))}"
            )

        return dict.fromkeys(intersection, ARTIFACT_SHARED_REPO_NAME)

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

        # Build the effective verify mapping: auto-detected entries are
        # overridden by any manually specified ones.
        effective_verify: dict[str, str] = {}
        if self.data.auto:
            effective_verify.update(self._build_auto_verify(guest))
        effective_verify.update(self.data.verify)

        if not effective_verify:
            self.verbose('No packages to verify.')
            return outcome

        self.info(
            fmf.utils.listed(list(effective_verify.keys()), 'package'),
            color='green',
        )

        try:
            package_origins = guest.package_manager.get_package_origin(effective_verify.keys())
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
        for package, expected_repo in effective_verify.items():
            actual_origin = package_origins[package]

            if actual_origin == expected_repo:
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
            if actual_origin is SpecialPackageOrigin.NOT_INSTALLED:
                note = (
                    f"Package '{package}': expected repo"
                    f" '{expected_repo}', but the package is not installed."
                )
            else:
                note = (
                    f"Package '{package}': expected repo"
                    f" '{expected_repo}', actual '{actual_origin}'."
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
