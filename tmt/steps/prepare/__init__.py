import collections
import copy
import dataclasses
from typing import (TYPE_CHECKING, Any, DefaultDict, Dict, List, Optional,
                    Type, cast)

import click
import fmf
import fmf.utils

import tmt
import tmt.steps
import tmt.steps.provision
from tmt.steps import Action
from tmt.utils import GeneralError, uniq

if TYPE_CHECKING:
    import tmt.base
    import tmt.cli
    from tmt.base import Plan


@dataclasses.dataclass
class PrepareStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    pass


class _RawPrepareStepData(tmt.steps._RawStepData, total=False):
    package: List[str]
    missing: str
    roles: DefaultDict[str, List[str]]
    hosts: Dict[str, str]
    order: int
    summary: str


class PreparePlugin(tmt.steps.Plugin):
    """ Common parent of prepare plugins """

    _data_class = PrepareStepData

    # List of all supported methods aggregated from all plugins of the same step.
    _supported_methods: List[tmt.steps.Method] = []

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[Type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all prepare plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Prepare.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @click.option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for environment preparation.')
        def prepare(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('prepare')
            Prepare._save_context(context)

        return prepare

    def go(
            self,
            *,
            guest: 'tmt.steps.provision.Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Prepare the guest (common actions) """
        super().go(guest=guest, environment=environment, logger=logger)

        # Show guest name first in multihost scenarios
        if self.step.plan.provision.is_multihost:
            logger.info('guest', guest.name, 'green')

        # Show requested role if defined
        # FIXME: cast() - typeless "dispatcher" method
        where = cast(List[str], self.get('where'))
        if where:
            logger.info('where', fmf.utils.listed(where), 'green')


class Prepare(tmt.steps.Step):
    """
    Prepare the environment for testing.

    Use the 'order' attribute to select in which order preparation
    should happen if there are multiple configs. Default order is '50'.
    Default order of required packages installation is '70', for the
    recommended packages it is '75'.
    """

    _plugin_base_class = PreparePlugin

    def __init__(
            self,
            *,
            plan: 'Plan',
            data: tmt.steps.RawStepDataArgument,
            logger: tmt.log.Logger) -> None:
        """ Initialize prepare step data """
        super().__init__(plan=plan, data=data, logger=logger)
        self.preparations_applied = 0

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(PreparePlugin, PreparePlugin.delegate(self, data=data))
            plugin.wake()
            # Add plugin only if there are data
            if not plugin.data.is_bare:
                self._phases.append(plugin)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.debug(
                'Prepare wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """ Give a concise summary of the preparation """
        preparations = fmf.utils.listed(
            self.preparations_applied, 'preparation')
        self.info('summary', f'{preparations} applied', 'green', shift=1)

    def _prepare_roles(self) -> DefaultDict[str, List[str]]:
        """ Create a mapping of roles to guest names """
        role_mapping = collections.defaultdict(list)
        for guest in self.plan.provision.guests():
            if guest.role:
                role_mapping[guest.role].append(guest.name)
        return role_mapping

    def _prepare_hosts(self) -> Dict[str, str]:
        """ Create a mapping of guest names to IP addresses """
        host_mapping = {}
        for guest in self.plan.provision.guests():
            if hasattr(guest, 'guest') and guest.guest:
                # FIXME: guest.guest may not be simply an IP address but also
                #        a host name.
                host_mapping[guest.name] = guest.guest
        return host_mapping

    def go(self) -> None:
        """ Prepare the guests """
        super().go()

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        import tmt.base

        # Required packages
        requires = uniq([
            *self.plan.discover.requires(),
            *self.plan.provision.requires(),
            *self.plan.prepare.requires(),
            *self.plan.execute.requires(),
            *self.plan.report.requires(),
            *self.plan.finish.requires()
            ])

        if requires:
            data: _RawPrepareStepData = dict(
                how='install',
                name='requires',
                summary='Install required packages',
                order=tmt.utils.DEFAULT_PLUGIN_ORDER_REQUIRES,
                package=[
                    require.to_spec()
                    for require in tmt.base.assert_simple_requirements(
                        requires,
                        'After beakerlib processing, tests may have only simple requirements',
                        self._logger)
                    ])
            self._phases.append(PreparePlugin.delegate(self, raw_data=data))

        # Recommended packages
        recommends = uniq(self.plan.discover.recommends())
        if recommends:
            data = dict(
                how='install',
                name='recommends',
                summary='Install recommended packages',
                order=tmt.utils.DEFAULT_PLUGIN_ORDER_RECOMMENDS,
                package=[
                    recommend.to_spec()
                    for recommend in tmt.base.assert_simple_requirements(
                        recommends,
                        'After beakerlib processing, tests may have only simple requirements',
                        self._logger)
                    ],
                missing='skip')
            self._phases.append(PreparePlugin.delegate(self, raw_data=data))

        # Implicit multihost setup
        if self.plan.provision.is_multihost:
            data = dict(
                how='multihost',
                name='multihost',
                summary='Setup guest for multihost testing',
                order=tmt.utils.DEFAULT_PLUGIN_ORDER_MULTIHOST,
                roles=self._prepare_roles(),
                hosts=self._prepare_hosts(),
                )
            self._phases.append(PreparePlugin.delegate(self, raw_data=data))

        # Prepare guests (including workdir sync)
        for guest in self.plan.provision.guests():
            guest.push()
            # Create a guest copy and change its parent so that the
            # operations inside prepare plugins on the guest use the
            # prepare step config rather than provision step config.
            guest_copy = copy.copy(guest)
            guest_copy.inject_logger(
                guest._logger.clone().apply_verbosity_options(**self._options))
            guest_copy.parent = self
            # Execute each prepare plugin
            for phase in self.phases(classes=(Action, PreparePlugin)):
                if not phase.enabled_on_guest(guest_copy):
                    continue

                if isinstance(phase, Action):
                    phase.go()

                elif isinstance(phase, PreparePlugin):
                    # TODO: re-injecting the logger already given to the guest,
                    # with multihost support heading our way this will change
                    # to be not so trivial.
                    phase.go(guest=guest_copy, logger=guest_copy._logger)

                    self.preparations_applied += 1

                else:
                    raise GeneralError(f'Unexpected phase in prepare step: {phase}')

                self.info('')

            # Pull artifacts created in the plan data directory
            # if there was at least one plugin executed
            if self.phases():
                guest_copy.pull(self.plan.data_directory)

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()
