from typing import Any, Optional, cast

import fmf.utils

import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.log import Logger
from tmt.result import PhaseResult, ResultGuestData, ResultOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.utils import Environment


def _normalize_verify_mappings(
    key_address: str,
    value: Any,
    logger: Logger,
) -> dict[str, str]:
    """Normalize verify mappings from a dict mapping package names to expected repos."""
    if not isinstance(value, dict):
        raise tmt.utils.NormalizationError(
            key_address, value, "a dict mapping package names to expected repo names"
        )
    # ignore[redundant-cast]: mypy infers `dict[Any, Any]` after the isinstance check
    # while pyright settles for `dict[Unknown, Unknown]`; the cast helps pyright.
    return {str(k): str(v) for k, v in cast(dict[Any, Any], value).items()}  # type: ignore[redundant-cast]


@container
class PrepareVerifyInstallationData(PrepareStepData):
    """Data class for verify-installation prepare plugin."""

    @classmethod
    def pre_normalization(cls, raw_data: tmt.steps._RawStepData, logger: Logger) -> None:
        super().pre_normalization(raw_data, logger)
        name = raw_data.get('name')
        if name is not None and name.startswith(tmt.utils.DEFAULT_NAME):
            raw_data['name'] = 'verify-installation'

    order: int = field(
        default=tmt.steps.PHASE_ORDER_PREPARE_VERIFY_INSTALLATION,
        help='Order in which the phase should be handled.',
    )

    verify: dict[str, str] = field(
        default_factory=dict,
        help="Mapping of package names to expected source repository names.",
        normalize=_normalize_verify_mappings,
        serialize=lambda d: d,
        unserialize=lambda data: cast(dict[str, str], data),
    )


@tmt.steps.provides_method('verify-installation')
class PrepareVerifyInstallation(PreparePlugin[PrepareVerifyInstallationData]):
    """
    Verify that installed packages came from expected repositories.

    This plugin checks that installed packages were actually installed
    from the expected repositories. It runs after package installation
    to verify the ground truth of where packages came from.

    .. note::

        Currently only supports DNF-based package managers (``dnf``,
        ``dnf5``). Other package managers will cause the step to fail with
        an unsupported error.

    .. note::

        On ``dnf5``, packages installed as part of a kiwi container image
        build report a random UUID as their source repository (the mapping
        between the UUID and the original repo is discarded after the build).
        Such packages are attributed to ``KIWI-PREBAKED`` and can be matched
        with ``expected-repo: KIWI-PREBAKED`` in the verification mapping.

    .. warning::

        Verification failures are recorded as ``FAIL`` results in the
        prepare phase output and cause the prepare step to fail, preventing
        test execution.

    Example usage:

    .. code-block:: yaml

        prepare:
            how: verify-installation
            verify:
                make: fedora
                gcc: fedora
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

        try:
            package_origins = guest.package_manager.get_package_origin(self.data.verify.keys())
        except (NotImplementedError, tmt.utils.RunError) as err:
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
        for package, expected_repo in self.data.verify.items():
            actual_repo = package_origins.get(package)

            if actual_repo == expected_repo:
                outcome.results.append(
                    PhaseResult(
                        name=f'{self.name} / {package}',
                        result=ResultOutcome.PASS,
                        note=[
                            f"Package '{package}' installed from expected repo '{actual_repo}'."
                        ],
                        guest=ResultGuestData.from_guest(guest=guest),
                    )
                )
                continue

            failed_packages.append(package)
            if actual_repo is None:
                note = (
                    f"Package '{package}': expected repo"
                    f" '{expected_repo}', but the package is not installed"
                    f" or its source repository could not be determined."
                )
            else:
                note = (
                    f"Package '{package}': expected repo"
                    f" '{expected_repo}', actual '{actual_repo}'."
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
            # FIXME: once https://github.com/teemtee/tmt/pull/4667 is merged,
            # the explicit exception appended here may no longer be needed —
            # the prepare step will recognise FAIL outcomes and stop the run
            # without requiring an attached exception.
            outcome.exceptions.append(
                tmt.utils.PrepareError(
                    f"Package source verification failed for: {', '.join(failed_packages)}"
                )
            )
        else:
            self.info('All packages verified successfully.', color='green')

        return outcome
