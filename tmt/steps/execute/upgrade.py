from typing import Any, Optional, Union, cast

import fmf.utils

import tmt.base
import tmt.log
import tmt.result
import tmt.steps
import tmt.steps.discover.fmf
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.container import container, field, key_to_option
from tmt.steps.discover import Discover, DiscoverPlugin, DiscoverStepData
from tmt.steps.discover.fmf import DiscoverFmf, DiscoverFmfStepData, normalize_ref
from tmt.steps.execute import ExecutePlugin
from tmt.steps.execute.internal import ExecuteInternal, ExecuteInternalData
from tmt.steps.prepare import PreparePlugin
from tmt.steps.prepare.install import PrepareInstallData
from tmt.utils import Environment, EnvVarValue, Path

STATUS_VARIABLE = 'IN_PLACE_UPGRADE'
BEFORE_UPGRADE_PREFIX = 'old'
DURING_UPGRADE_PREFIX = 'upgrade'
AFTER_UPGRADE_PREFIX = 'new'
UPGRADE_DIRECTORY = 'upgrade'

PROPAGATE_TO_DISCOVER_KEYS = ['url', 'ref', 'filter', 'test', 'exclude', 'upgrade_path']


@container
class ExecuteUpgradeData(ExecuteInternalData):
    url: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-u', '--url'),
        metavar='REPOSITORY',
        help='URL of the git repository with upgrade tasks.',
    )
    upgrade_path: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-p', '--upgrade-path'),
        metavar='PLAN_NAME',
        help='Upgrade path corresponding to a plan name in the repository with upgrade tasks.',
    )

    # "Inherit" from tmt.steps.discover.fmf.DiscoverFmfStepData
    ref: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-r', '--ref'),
        metavar='REVISION',
        help='Branch, tag or commit specifying the git revision.',
        normalize=normalize_ref,
    )
    test: list[str] = field(
        default_factory=list,
        option=('-t', '--test'),
        metavar='NAMES',
        multiple=True,
        help='Select tests by name.',
        normalize=tmt.utils.normalize_string_list,
    )
    filter: list[str] = field(
        default_factory=list,
        option=('-F', '--filter'),
        metavar='FILTERS',
        multiple=True,
        help='Include only tests matching the filter.',
        normalize=tmt.utils.normalize_string_list,
    )
    exclude: list[str] = field(
        default_factory=list,
        option=('-x', '--exclude'),
        metavar='REGEXP',
        multiple=True,
        help="Exclude a regular expression from search result.",
        normalize=tmt.utils.normalize_string_list,
    )


@tmt.steps.provides_method('upgrade')
class ExecuteUpgrade(ExecuteInternal):
    """
    Perform system upgrade during testing.

    In order to enable developing tests for upgrade testing, we need to provide
    a way how to execute these tests easily. This does not cover unit tests for
    individual actors but rather system tests which verify
    the whole upgrade story.

    The upgrade executor runs the discovered tests (using the internal
    executor), then performs a set of upgrade tasks from a remote
    repository, and finally, re-runs the tests on the upgraded guest.

    The ``IN_PLACE_UPGRADE`` environment variable is set during the test
    execution to differentiate between the stages of the test. It is set
    to ``old`` during the first execution and ``new`` during the second
    execution. Test names are prefixed with this value to make the names
    unique. Based on this variable, the test can perform appropriate actions.

    * ``old``: setup, test
    * ``new``: test, cleanup
    * ``without``: setup, test, cleanup

    The upgrade tasks performing the actual system upgrade are taken
    from a remote repository (specified by the ``url`` key) based on an upgrade
    path (e.g. ``fedora35to36``) or other filters (e.g. specified by the
    ``filter`` key). If both ``upgrade-path`` and extra filters are specified,
    the discover keys in the remote upgrade path plan are overridden by the
    filters specified in the local plan.

    The upgrade path must correspond to a plan name in the
    remote repository whose discover step selects tests (upgrade tasks)
    performing the upgrade. Currently, selection of upgrade tasks in the remote
    repository can be done using both fmf and shell discover method.
    If the ``url`` is not provided, upgrade path and upgrade tasks are taken from
    the current repository. The supported keys in discover are:

    * ``ref``
    * ``filter``
    * ``exclude``
    * ``tests``
    * ``test``

    The environment variables defined in the remote upgrade path plan are
    passed to the upgrade tasks when they are executed. An example of an
    upgrade path plan (in the remote repository):

    .. code-block:: yaml

        discover: # Selects appropriate upgrade tasks (L1 tests)
            how: fmf
            filter: "tag:fedora"
        environment: # This is passed to upgrade tasks
            SOURCE: 35
            TARGET: 36
        execute:
            how: tmt

    If no upgrade path is specified in the plan, the tests (upgrade tasks)
    are selected based on the configuration of the upgrade plugin
    (e.g. based on the filter in its configuration).

    If these two possible ways of specifying upgrade tasks are combined,
    the remote discover plan is used but its options are overridden
    with the values specified locally.

    The same options and config keys and values can be used as in the
    internal executor.

    Minimal execute config example with an upgrade path:

    .. code-block:: yaml

        execute:
            how: upgrade
            url: https://github.com/teemtee/upgrade
            upgrade-path: /paths/fedora35to36

    Execute config example without an upgrade path:

    .. code-block:: yaml

        execute:
            how: upgrade
            url: https://github.com/teemtee/upgrade
            filter: "tag:fedora"

    .. code-block:: yaml

        # A simple beakerlib test using the $IN_PLACE_UPGRADE variable
        . /usr/share/beakerlib/beakerlib.sh || exit 1

        VENV_PATH=/var/tmp/venv_test

        rlJournalStart
            # Perform the setup only for the old distro
            if [[ "$IN_PLACE_UPGRADE" !=  "new" ]]; then
                rlPhaseStartSetup
                    rlRun "python3.9 -m venv $VENV_PATH"
                    rlRun "$VENV_PATH/bin/pip install pyjokes"
                rlPhaseEnd
            fi

            # Execute the test for both old & new distro
            rlPhaseStartTest
                rlAsssertExists "$VENV_PATH/bin/pyjoke"
                rlRun "$VENV_PATH/bin/pyjoke"
            rlPhaseEnd

            # Skip the cleanup phase when on the old distro
            if [[ "$IN_PLACE_UPGRADE" !=  "old" ]]; then
                rlPhaseStartCleanup
                    rlRun "rm -rf $VENV_PATH"
                rlPhaseEnd
            fi
        rlJournalEnd
    """

    _data_class = ExecuteUpgradeData
    data: ExecuteUpgradeData

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._discover_upgrade: Optional[DiscoverFmf] = None

    @property  # type:ignore[override]
    def discover(self) -> Union[Discover, DiscoverFmf]:
        """
        Return discover plugin instance
        """

        # If we are in the second phase (upgrade), take tests from our fake
        # discover plugin.
        if self._discover_upgrade:
            return self._discover_upgrade
        return self.step.plan.discover

    @discover.setter
    def discover(self, plugin: Optional[DiscoverPlugin[DiscoverStepData]]) -> None:
        self._discover = plugin

    def go(
        self,
        *,
        guest: 'tmt.steps.provision.Guest',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Execute available tests
        """

        # Inform about the how, skip the actual execution
        ExecutePlugin.go(self, guest=guest, environment=environment, logger=logger)

        self.url = self.get('url')
        self.upgrade_path = self.get('upgrade-path')
        for key in self._keys:
            value = self.get(key)
            if value:
                if key == "test":
                    self.info('test', fmf.utils.listed(value), 'green')
                else:
                    self.info(key, value, color='green')

        # Nothing to do in dry mode
        if self.is_dry_run:
            self._results = []
            return

        self.verbose('upgrade', 'run tests on the old system', color='blue', shift=1)
        self._run_test_phase(guest, BEFORE_UPGRADE_PREFIX, logger)
        self.verbose('upgrade', 'perform the system upgrade', color='blue', shift=1)
        self._perform_upgrade(guest, logger)
        self.verbose('upgrade', 'run tests on the new system', color='blue', shift=1)
        self._run_test_phase(guest, AFTER_UPGRADE_PREFIX, logger)

    def _get_plan(self, upgrades_repo: Path) -> tmt.base.Plan:
        """
        Get plan based on upgrade path
        """

        tree = tmt.base.Tree(logger=self._logger, path=upgrades_repo)
        try:
            # We do not want to consider plan -n provided on the command line
            # in the remote repo for finding upgrade path.
            tmt.base.Plan.ignore_class_options = True
            plans = tree.plans(names=[self.upgrade_path])
        finally:
            tmt.base.Plan.ignore_class_options = False

        if len(plans) == 0:
            raise tmt.utils.ExecuteError(
                f"No matching upgrade path found for '{self.upgrade_path}'."
            )
        if len(plans) > 1:
            names = [plan.name for plan in plans]
            raise tmt.utils.ExecuteError(
                f"Ambiguous upgrade path reference, found plans {fmf.utils.listed(names)}."
            )
        return plans[0]

    def _fetch_upgrade_tasks(self) -> None:
        """
        Fetch upgrade tasks using DiscoverFmf
        """

        data = DiscoverFmfStepData(
            name='upgrade-discover',
            how='fmf',
            # url=self.data.url,
            **{key: getattr(self.data, key) for key in PROPAGATE_TO_DISCOVER_KEYS},
        )

        self._discover_upgrade = DiscoverFmf(logger=self._logger, step=self.step, data=data)
        self._run_discover_upgrade()

    def _run_discover_upgrade(self) -> None:
        """
        Silently run discover upgrade
        """

        # Make it quiet, we do not want any output from discover
        assert self._discover_upgrade is not None

        # Discover normally uses also options from global Test class
        # (e.g. test -n foo). Ignore this when selecting upgrade tasks.
        tmt.base.Test.ignore_class_options = True

        cli_invocation = self._discover_upgrade.cli_invocation
        if cli_invocation:
            quiet, cli_invocation.options['quiet'] = cli_invocation.options['quiet'], True

        try:
            self._discover_upgrade.wake()
            self._discover_upgrade.go()

        finally:
            tmt.base.Test.ignore_class_options = False

            if cli_invocation:
                cli_invocation.options['quiet'] = quiet

    def _install_dependencies(
        self,
        guest: tmt.steps.provision.Guest,
        dependencies: list[tmt.base.DependencySimple],
        recommends: bool = False,
    ) -> None:
        """
        Install packages required/recommended for upgrade
        """

        phase_name = 'recommended' if recommends else 'required'
        data = PrepareInstallData(
            how='install',
            name=f'{phase_name}-packages-upgrade',
            summary=f'Install packages {phase_name} by the upgrade',
            package=tmt.utils.uniq(dependencies),
            missing='skip' if recommends else 'fail',
        )

        PreparePlugin.delegate(self.step, data=data).go(  # type:ignore[attr-defined]
            guest=guest, logger=self._logger
        )

    def _prepare_remote_discover_data(self, plan: tmt.base.Plan) -> tmt.steps._RawStepData:
        """
        Merge remote discover data with the local filters
        """

        if len(plan.discover.data) > 1:
            raise tmt.utils.ExecuteError("Multiple discover configs are not supported.")

        data = plan.discover.data[0]

        remote_raw_data: tmt.steps._RawStepData = {
            # Force name
            'name': 'upgrade-discover-remote',
            'how': 'fmf',
        }
        remote_raw_data.update(
            cast(
                tmt.steps._RawStepData,
                {
                    key_to_option(key): value
                    for key, value in data.items()
                    if key in PROPAGATE_TO_DISCOVER_KEYS
                },
            )
        )

        # Local values have priority, override
        for key in self._keys:
            value = self.get(key)
            if key in PROPAGATE_TO_DISCOVER_KEYS and value:
                remote_raw_data[key] = value  # type:ignore[literal-required]

        return remote_raw_data

    def _perform_upgrade(self, guest: tmt.steps.provision.Guest, logger: tmt.log.Logger) -> None:
        """
        Perform a system upgrade
        """

        original_discover_phase = self.discover_phase

        try:
            self._fetch_upgrade_tasks()
            extra_environment = None
            assert self._discover_upgrade is not None
            if self.upgrade_path:
                # Create a fake discover from the data in the upgrade path
                plan = self._get_plan(self._discover_upgrade.testdir)
                data = self._prepare_remote_discover_data(plan)
                # Unset `url` because we don't want discover step to perform clone. Instead,
                # we want it to reuse existing, already cloned path.
                # ignore[typeddict-unknown-key]: data is _RwStepData, we do not have more detailed
                # type for raw step data of internal/upgrade plugins, it would be pretty verbose.
                data['url'] = None  # type: ignore[typeddict-unknown-key]
                data['path'] = self._discover_upgrade.testdir  # type:ignore[typeddict-unknown-key]
                # FIXME: cast() - https://github.com/teemtee/tmt/issues/1599
                self._discover_upgrade = cast(
                    DiscoverFmf, DiscoverPlugin.delegate(self.step, raw_data=data)
                )
                self._run_discover_upgrade()
                # Pass in the path-specific env variables
                extra_environment = plan.environment

            required_packages: list[tmt.base.DependencySimple] = []
            recommended_packages: list[tmt.base.DependencySimple] = []
            for test_origin in self._discover_upgrade.tests(enabled=True):
                test = test_origin.test

                test.name = f'/{DURING_UPGRADE_PREFIX}/{test.name.lstrip("/")}'

                # Gathering dependencies for upgrade tasks
                required_packages += tmt.base.assert_simple_dependencies(
                    test.require,
                    'After beakerlib processing, tests may have only simple requirements',
                    self._logger,
                )

                recommended_packages += tmt.base.assert_simple_dependencies(
                    test.recommend,
                    'After beakerlib processing, tests may have only simple requirements',
                    self._logger,
                )

                required_packages += test.test_framework.get_requirements(test, self._logger)

                for check in test.check:
                    required_packages += check.plugin.essential_requires(guest, test, self._logger)

            self._install_dependencies(guest, required_packages)
            self._install_dependencies(guest, recommended_packages, recommends=True)
            self.discover_phase = self._discover_upgrade.name
            self._run_tests(guest=guest, extra_environment=extra_environment, logger=logger)
        finally:
            self._discover_upgrade = None
            self.discover_phase = original_discover_phase

    def _run_test_phase(
        self, guest: tmt.steps.provision.Guest, prefix: str, logger: tmt.log.Logger
    ) -> None:
        """
        Execute a single test phase on the guest

        Tests names are prefixed with the prefix argument in order to make
        their names unique so that the results are distinguishable.
        The prefix is also set as IN_PLACE_UPGRADE environment variable.
        """

        names_backup = []
        for test_origin in self.discover.tests(enabled=True):
            names_backup.append(test_origin.test.name)
            test_origin.test.name = f'/{prefix}/{test_origin.test.name.lstrip("/")}'

        self._run_tests(
            guest=guest,
            extra_environment=Environment({STATUS_VARIABLE: EnvVarValue(prefix)}),
            logger=logger,
        )

        self._remove_old_results(prefix)

        for i, test_origin in enumerate(self.discover.tests(enabled=True)):
            test_origin.test.name = names_backup[i]

    def _remove_old_results(self, prefix: str) -> None:
        """
        Remove old results that were replaced by prefixed ones
        """

        results = self.step.plan.execute.results()
        old_result_names = [
            result.name.removeprefix(f'/{prefix}')
            for result in results
            if result.name.startswith(f'/{prefix}/')
        ]

        self.step.plan.execute._results = [
            result for result in results if result.name not in old_result_names
        ]
        self.step.plan.execute.save()
