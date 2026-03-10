from typing import Any, Optional, cast

import fmf.utils

import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.log import Logger
from tmt.package_managers import Package
from tmt.result import PhaseResult, ResultGuestData, ResultOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.utils import Environment


@container
class VerifyMapping:
    """A single package-to-repository verification mapping."""

    package: Package
    expected_repo: str

    def to_spec(self) -> dict[str, str]:
        return {'package': str(self.package), 'expected-repo': self.expected_repo}

    @classmethod
    def from_spec(cls, data: dict[str, str]) -> 'VerifyMapping':
        return cls(
            package=Package(data['package']),
            # Support both hyphen (canonical) and underscore (legacy serialised runs)
            expected_repo=data.get('expected-repo', data.get('expected_repo', '')),
        )


def _normalize_verify_mappings(
    key_address: str,
    value: Any,
    logger: Logger,
) -> list[VerifyMapping]:
    """Normalize verify mappings from a list of dicts with 'package' and 'expected-repo' keys."""
    if not isinstance(value, list):
        raise tmt.utils.NormalizationError(
            key_address, value, "a list of dicts with 'package' and 'expected-repo' keys"
        )
    # ignore[redundant-cast]: mypy infers the type to be `list[Any]` while pyright settles
    # for `list[Unknown]`; the cast helps pyright but mypy considers it redundant.
    return [
        VerifyMapping.from_spec(cast(dict[str, str], item))
        for item in cast(list[Any], value)  # type: ignore[redundant-cast]
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
        help="List of package and expected repository mappings.",
        normalize=_normalize_verify_mappings,
        serialize=lambda mappings: [m.to_spec() for m in mappings],
        unserialize=lambda data: [
            VerifyMapping.from_spec(item) for item in cast(list[dict[str, str]], data)
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

        Currently only supports DNF-based package managers (dnf, dnf5).
        Other package managers will cause the step to fail. Note that
        legacy ``yum`` (not a dnf symlink) may not support the
        ``repoquery --queryformat`` syntax used by this plugin.

    .. note::

        On ``dnf5``, packages installed as part of a kiwi container image build
        report a random UUID as their source repository (the mapping between the
        UUID and the original repo is discarded after the build). Such packages
        are attributed to ``DEFAULT-SYSTEM-REPO`` and can be matched with
        ``expected-repo: DEFAULT-SYSTEM-REPO`` in the verification mapping.

    .. warning::

        Verification failures are recorded as ``FAIL`` results in the
        prepare phase output and cause the prepare step to fail, preventing
        test execution.

    Example usage:

    .. code-block:: yaml

        prepare:
            how: verify-installation
            verify:
                - package: make
                  expected-repo: fedora
                - package: gcc
                  expected-repo: fedora
    """

    _data_class = PrepareVerifyInstallationData

    def go(
        self,
        *,
        guest: Guest,
        environment: Optional[Environment] = None,
        logger: Logger,
    ) -> tmt.steps.PluginOutcome:
        outcome = super().go(guest=guest, environment=environment, logger=logger)

        if self.is_dry_run:
            return outcome

        if not self.data.verify:
            self.verbose('No packages to verify.')
            return outcome

        self.info(
            fmf.utils.listed([m.package for m in self.data.verify], 'package'),
            color='green',
        )

        try:
            installed_repos = guest.package_manager.get_installed_repos(
                m.package for m in self.data.verify
            )
        except NotImplementedError as err:
            raise tmt.utils.PrepareError(
                f"Package source verification not supported for "
                f"'{guest.facts.package_manager}' package manager."
            ) from err
        except tmt.utils.RunError as err:
            outcome.results.append(
                PhaseResult(
                    name=self.name,
                    result=ResultOutcome.ERROR,
                    note=[f"Failed to query package repositories: {err}"],
                    guest=ResultGuestData.from_guest(guest=guest),
                )
            )
            outcome.exceptions.append(err)
            return outcome

        has_failures = False
        for verify_mapping in self.data.verify:
            actual_repo = installed_repos.get(verify_mapping.package)

            if actual_repo == verify_mapping.expected_repo:
                continue

            has_failures = True
            if actual_repo is None:
                note = (
                    f"Package '{verify_mapping.package}': expected repo"
                    f" '{verify_mapping.expected_repo}', but the package is not installed"
                    f" or its source repository could not be determined."
                )
            else:
                note = (
                    f"Package '{verify_mapping.package}': expected repo"
                    f" '{verify_mapping.expected_repo}', actual '{actual_repo}'."
                )

            outcome.results.append(
                PhaseResult(
                    name=verify_mapping.package,
                    result=ResultOutcome.FAIL,
                    note=[note],
                    guest=ResultGuestData.from_guest(guest=guest),
                )
            )

        if has_failures:
            failed = [r.name for r in outcome.results if r.result == ResultOutcome.FAIL]
            # FIXME: once https://github.com/teemtee/tmt/pull/4667 is merged,
            # the explicit exception appended here may no longer be needed —
            # the prepare step will recognise FAIL outcomes and stop the run
            # without requiring an attached exception.
            outcome.exceptions.append(
                tmt.utils.PrepareError(
                    f"Package source verification failed for: {', '.join(failed)}"
                )
            )
        else:
            self.info('All packages verified successfully.', color='green')

        return outcome
