
""" Step Classes """

import collections
import dataclasses
import functools
import itertools
import re
import shutil
import textwrap
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    DefaultDict,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypedDict,
    TypeVar,
    Union,
    cast,
    overload,
    )

import click
from click import echo
from click.core import ParameterSource

import tmt.export
import tmt.log
import tmt.options
import tmt.utils
from tmt.options import option, show_step_method_hints
from tmt.queue import GuestlessTask, Queue, Task, TaskOutcome
from tmt.utils import (
    DEFAULT_NAME,
    EnvironmentType,
    GeneralError,
    Path,
    cached_property,
    field,
    flatten,
    key_to_option,
    option_to_key,
    )

if TYPE_CHECKING:
    from typing_extensions import Self

    import tmt.base
    import tmt.cli
    import tmt.plugins
    import tmt.steps.discover
    import tmt.steps.execute
    from tmt.base import Plan
    from tmt.steps.provision import Guest


DEFAULT_PLUGIN_METHOD_ORDER: int = 50


# Supported steps and actions
STEPS: List[str] = ['discover', 'provision', 'prepare', 'execute', 'report', 'finish']
ACTIONS: List[str] = ['login', 'reboot']

# Step phase order
PHASE_START = 10
PHASE_BASE = 50
PHASE_END = 90

TEST_TOPOLOGY_FILENAME_BASE = 'tmt-test-topology'


PHASE_OPTIONS = tmt.options.create_options_decorator([
    option(
        '--insert',
        is_flag=True,
        default=False,
        help='Add this phase instead of overwriting the existing ones.'),
    option(
        '--update',
        is_flag=True,
        default=False,
        help="""
            Update existing phase. Use --name to specify which one, or omit --name
            and update all existing phases.
            """),
    option(
        '--update-missing',
        is_flag=True,
        default=False,
        help="""
            Update existing phase, but make changes to fields that were not set by fmf data
            or previous command line options. Use --name to specify which one, or omit --name and
            update all existing phases.
            """),
    option(
        '--name',
        type=str,
        help="Name of the existing phase which should be updated when '--update' is used."),
    option(
        '--order',
        type=int,
        default=DEFAULT_PLUGIN_METHOD_ORDER,
        help='Order in which the phase should be handled.')
    ])


class DefaultNameGenerator:
    """
    Generator of names for that do not have any.

    If user did not set any ``name`` for one or more phases, tmt
    will assign them a "dummy" name ``default-N``. This class wraps
    the generator.
    """

    def __init__(self, known_names: List[str]) -> None:
        """
        Generator of names for that do not have any.

        :param known_names: already existing names the generator
            needs to avoid.
        """

        self.known_names = known_names

        self.restart()

    @classmethod
    def from_raw_phases(cls, raw_data: Iterable['_RawStepData']) -> 'DefaultNameGenerator':
        """
        Create a generator based on available phase specifications.

        A special constructor that extracts ``known_names`` from ``raw_data``.

        :param raw_data: phase specifications as collected from fmf nodes and
            CLI options.
        """

        collected_name_keys = [raw_datum.get('name') for raw_datum in raw_data]
        actual_name_keys = [name for name in collected_name_keys if name]

        return DefaultNameGenerator(actual_name_keys)

    def restart(self) -> None:
        """ Reset the generator and start from the beginning again """

        def _generator() -> Generator[str, None, None]:
            for i in itertools.count(start=0):
                name = f'{DEFAULT_NAME}-{i}'

                if name in self.known_names:
                    continue

                self.known_names.append(name)
                yield name

        self.generator = _generator()

    def get(self) -> str:
        return next(self.generator)


class Phase(tmt.utils.Common):
    """ A phase of a step """

    def __init__(
            self,
            *,
            order: int = tmt.utils.DEFAULT_PLUGIN_ORDER,
            **kwargs: Any):
        super().__init__(**kwargs)
        self.order: int = order

    def enabled_on_guest(self, guest: 'Guest') -> bool:
        """ Phases are enabled across all guests by default """
        return True

    @property
    def is_in_standalone_mode(self) -> bool:
        """
        True if the phase is in stand-alone mode.

        Stand-alone mode means that only this phase should be run as a part
        of the run (and not any other even if requested using --all).
        This is useful as some plugin options may completely change its
        behaviour from the regular behaviour based on options
        (e.g. listing images inside a provision plugin).
        """
        return False


# A variable used to describe a generic type for all classes derived from Phase
PhaseT = TypeVar('PhaseT', bound=Phase)

# A type alias for plugin classes
PluginClass = Type['BasePlugin']

_RawStepData = TypedDict('_RawStepData', {
    'how': str,
    'name': str
    }, total=False)


RawStepDataArgument = Union[_RawStepData, List[_RawStepData]]


T = TypeVar('T', bound='StepData')


@dataclasses.dataclass
class StepData(
        tmt.utils.SpecBasedContainer[_RawStepData, _RawStepData],
        tmt.utils.NormalizeKeysMixin,
        tmt.utils.SerializableContainer):
    """
    Keys necessary to describe, create, save and restore a step.

    Very basic set of keys shared across all steps.

    Provides basic functionality for transition between "raw" step data, which
    consists of fmf nodes and CLI options, and this container representation with
    keys and types more suitable for internal use.

    Implementation expects simple 1:1 relation between ``StepData`` attributes - keys -
    and their fmf/CLI sources, where keys replace options' dashes (``-``) with
    underscores (``_``). For example, to hold value of an fmf key ``foo-bar`` - or
    value of a corresponding CLI option, ``--foo-bar``, a step data class should
    declare key named ``foo_data``. All ``StepData`` methods would honor this mapping.
    """

    # TODO: we can easily add lists of keys for various verbosity levels...
    _KEYS_SHOW_ORDER = ['name', 'how']

    name: str
    how: str
    order: int = tmt.utils.DEFAULT_PLUGIN_ORDER
    summary: Optional[str] = None

    def to_spec(self) -> _RawStepData:
        """ Convert to a form suitable for saving in a specification file """

        return cast(_RawStepData, {
            tmt.utils.key_to_option(key): value
            for key, value in self.items()
            })

    @classmethod
    def pre_normalization(cls, raw_data: _RawStepData, logger: tmt.log.Logger) -> None:
        """ Called before normalization, useful for tweaking raw data """

        logger.debug(f'{cls.__name__}: original raw data', str(raw_data), level=4)

    def post_normalization(self, raw_data: _RawStepData, logger: tmt.log.Logger) -> None:
        """ Called after normalization, useful for tweaking normalized data """

        pass

    # ignore[override]: expected, we need to accept one extra parameter, `logger`.
    @classmethod
    def from_spec(  # type: ignore[override]
            cls: Type[T],
            raw_data: _RawStepData,
            logger: tmt.log.Logger) -> T:
        """ Convert from a specification file or from a CLI option """

        cls.pre_normalization(raw_data, logger)

        data = cls(name=raw_data['name'], how=raw_data['how'])
        data._load_keys(cast(Dict[str, Any], raw_data), cls.__name__, logger)

        data.post_normalization(raw_data, logger)

        return data


@dataclasses.dataclass
class WhereableStepData:
    """
    Keys shared by step data that may be limited to a particular guest.

    To be used as a mixin class, adds necessary keys.

    See [1] and [2] for specification.

    1. https://tmt.readthedocs.io/en/stable/spec/plans.html#where
    2. https://tmt.readthedocs.io/en/stable/spec/plans.html#spec-plans-prepare-where
    """

    where: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list
        )


class Step(tmt.utils.MultiInvokableCommon, tmt.export.Exportable['Step']):
    """ Common parent of all test steps """

    # Default implementation for all steps is "shell", but some
    # steps like provision may have better defaults for their
    # area of expertise.
    DEFAULT_HOW: str = 'shell'

    # Refers to a base class for all plugins registered with this step.
    _plugin_base_class: PluginClass

    #: Stores the normalized step data. Initialized first time step's `data`
    #: is accessed.
    #
    # The delayed initialization is necessary to support `how` changes via
    # command-line - code instantiating steps must be able to invalidate
    # and replace raw step data entries before they get normalized and become
    # the single source of information for plugins involved.
    _data: List[StepData]

    #: Stores the original raw step data. Initialized by :py:meth:`__init__`
    #: or :py:meth:`wake`, and serves as a source for normalization performed
    #: by :py:meth:`_normalize_data`.
    _raw_data: List[_RawStepData]

    # The step has pruning capability to remove all irrelevant files. All
    # important file and directory names located in workdir should be specified
    # in the list below to avoid deletion during pruning.
    _preserved_workdir_members: List[str] = ['step.yaml']

    def __init__(
            self,
            *,
            plan: 'Plan',
            data: Optional[RawStepDataArgument] = None,
            name: Optional[str] = None,
            workdir: tmt.utils.WorkdirArgumentType = None,
            logger: tmt.log.Logger) -> None:
        """ Initialize and check the step data """
        logger.apply_verbosity_options(cli_invocation=self.__class__.cli_invocation)

        super().__init__(name=name, parent=plan, workdir=workdir, logger=logger)

        # Initialize data
        self.plan: 'Plan' = plan
        self._status: Optional[str] = None
        self._phases: List[Phase] = []

        # Normalize raw data to be a list of step configuration data, one item per
        # distinct step configuration. Make sure all items have `name`` and `how` keys.
        #
        # NOTE: this is not a normalization step as performed by NormalizeKeysMixin.
        # Here we make sure the raw data can be consumed by the delegation code, we
        # do not modify any existing content of raw data items.

        # Create an empty step by default (can be updated from cli)
        if data is None:
            self._raw_data = [{}]

        # Convert to list if only a single config provided
        elif isinstance(data, dict):
            self._raw_data = [data]

        # List is as good as it gets
        elif isinstance(data, list):
            self._raw_data = data

        # Shout about invalid configuration
        else:
            raise tmt.utils.GeneralError(
                f"Invalid '{self}' config in '{self.plan}'.")

        self._set_default_values(self._raw_data)

    def _check_duplicate_names(self, raw_data: List[_RawStepData]) -> None:
        """ Check for duplicate names in phases """

        for name in tmt.utils.duplicates(raw_datum.get('name', None) for raw_datum in raw_data):
            raise tmt.utils.GeneralError(f"Duplicate phase name '{name}' in step '{self.name}'.")

    def _set_default_values(self, raw_data: List[_RawStepData]) -> List[_RawStepData]:
        """ Set default values for ``name`` and ``how`` fields if not specified """

        name_generator = DefaultNameGenerator.from_raw_phases(raw_data)

        for _i, raw_datum in enumerate(raw_data):
            # Add default unique names even to multiple configs so that the users
            # don't need to specify it if they don't care about the name
            if raw_datum.get('name', None) is None:
                raw_datum['name'] = name_generator.get()

            # Set 'how' to the default if not specified
            if raw_datum.get('how', None) is None:
                raw_datum['how'] = self.DEFAULT_HOW

        return raw_data

    def _normalize_data(
            self,
            raw_data: List[_RawStepData],
            logger: tmt.log.Logger) -> List[StepData]:
        """
        Normalize step data entries.

        Every entry of ``raw_data`` is converted into an instance of
        :py:class:`StepData` or one of its subclasses. Particular class
        is derived from a plugin identified by raw data's ``how`` field
        and step's plugin registry.
        """

        self._check_duplicate_names(raw_data)

        data: List[StepData] = []

        for raw_datum in raw_data:
            plugin = self._plugin_base_class.delegate(self, raw_data=raw_datum)

            data.append(plugin.data)

        return data

    def _export(self, *, keys: Optional[List[str]] = None) -> tmt.export._RawExportedInstance:
        # TODO: one day, this should recurse down into each materialized plugin,
        # to give them chance to affect the export of their data.
        return cast(tmt.export._RawExportedInstance, self._raw_data)

    @property
    def step_name(self) -> str:
        return self.__class__.__name__.lower()

    @property
    def data(self) -> List[StepData]:
        if not hasattr(self, '_data'):
            self._data = self._normalize_data(self._raw_data, self._logger)

        return self._data

    @data.setter
    def data(self, data: List[StepData]) -> None:
        self._data = data

    @property
    def enabled(self) -> Optional[bool]:
        """ True if the step is enabled """
        if self.plan.my_run is None or self.plan.my_run._cli_context_object is None:
            return None

        return self.name in self.plan.my_run._cli_context_object.steps

    @property
    def plugins_in_standalone_mode(self) -> int:
        """
        The number of plugins in standalone mode.

        Stand-alone mode means that only this step should be run as a part
        of the run (and not any other even if requested using --all).
        This is useful as some step options may completely change its
        behaviour from the regular behaviour based on options
        (e.g. listing images inside provision).
        """
        return sum(phase.is_in_standalone_mode for phase in self.phases())

    @classmethod
    def usage(cls, method_overview: str) -> str:
        """ Prepare general usage message for the step """
        # Main description comes from the class docstring
        if cls.__name__ is None:
            raise tmt.utils.GeneralError("Missing name of the step.")

        if cls.__doc__ is None:
            raise tmt.utils.GeneralError(
                f"Missing docstring of the step {cls.__name__.lower()}.")

        usage = textwrap.dedent(cls.__doc__)
        # Append the list of supported methods
        usage += '\n\n' + method_overview
        # Give a hint about detailed help
        name = cls.__name__.lower()
        usage += (
            f"\n\nUse 'tmt run {name} --how <method> --help' to learn more "
            f"about given {name} method and all its supported options.")
        return usage

    def status(self, status: Optional[str] = None) -> Optional[str]:
        """
        Get and set current step status

        The meaning of the status is as follows:
        todo ... config, data and command line processed (we know what to do)
        done ... the final result of the step stored to workdir (we are done)
        """
        # Update status
        if status is not None:
            # Check for valid values
            if status not in ['todo', 'done']:
                raise tmt.utils.GeneralError(f"Invalid status '{status}'.")
            # Show status only if changed
            if self._status != status:
                self._status = status
                self.debug('status', status, color='yellow', level=2)
        # Return status
        return self._status

    def show(self) -> None:
        """ Show step details """

        for data in self.data:
            self._plugin_base_class.delegate(self, data=data).show()

    def load(self) -> None:
        """ Load status and step data from the workdir """
        try:
            raw_step_data: Dict[Any, Any] = tmt.utils.yaml_to_dict(self.read(Path('step.yaml')))
            self.debug('Successfully loaded step data.', level=2)

            self.data = [
                StepData.unserialize(raw_datum, self._logger)
                for raw_datum in raw_step_data['data']
                ]
            self._raw_data = [
                datum.to_spec()
                for datum in self.data
                ]
            self.status(raw_step_data['status'])
        except tmt.utils.GeneralError:
            self.debug('Step data not found.', level=2)

    def save(self) -> None:
        """ Save status and step data to the workdir """
        content: Dict[str, Any] = {
            'status': self.status(),
            'data': [datum.to_serialized() for datum in self.data]
            }
        self.write(Path('step.yaml'), tmt.utils.dict_to_yaml(content))

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        # Cleanup possible old workdir if called with --force
        if self.is_forced_run:
            self._workdir_cleanup()

        # Load stored data
        self.load()

        # Status 'todo' means the step has not finished successfully.
        # Probably interrupted in the middle. Clean up the work
        # directory to give it another chance with a fresh start.
        if self.status() == 'todo':
            self.debug("Step has not finished. Let's try once more!", level=2)
            self._workdir_cleanup()

        # Importing here to avoid circular imports
        import tmt.steps.report

        # Special handling for the report step to always enable force mode in
        # order to cover a very frequent use case 'tmt run --last report'
        # FIXME find a better way how to enable always-force per plugin
        if (isinstance(self, tmt.steps.report.Report) and
                self.data[0].how in ['display', 'html']):
            self.debug("Report step always force mode enabled.")
            self._workdir_cleanup()
            self.status('todo')

        # Nothing more to do when the step is already done
        if self.status() == 'done':
            self.debug('Step is done, not touching its data.')
            return

        # Override step data with command line options
        #
        # Do NOT iterate over `self.data`: reading `self.data` would trigger materialization
        # of its content, calling plugins owning various raw step data to create corresponding
        # `StepData` instances. That is actually harmful, as plugins that might be explicitly
        # overriden by `--how` option, would run, with unexpected side-effects.
        # Instead, iterate over raw data, and replace incompatible plugins with the one given
        # on command line. There is no reason to ever let dropped plugin's `StepData` to
        # materialize when it's going to be thrown away anyway.
        debug = functools.partial(self.debug, level=4, topic=tmt.log.Topic.CLI_INVOCATIONS)

        debug('Update phases by CLI invocations')

        def _to_raw_step_datum(options: Dict[str, Any]) -> _RawStepData:
            """
            Convert CLI options to fmf-like raw step data dictionary.

            This means dropping all keys that cannot come from an fmf node, like
            keys representing CLI options.
            """

            def _iter_options() -> Generator[Tuple[str, Any], None, None]:
                for name, value in options.items():
                    if name in ('update', 'update_missing', 'insert'):
                        continue

                    yield key_to_option(name), value

            return cast(
                _RawStepData,
                dict(_iter_options())
                )

        # In this list, we collect all known phases, represented by their raw step data. The list
        # will be inspected by code below, e.g. when evaluationg `--update` CLI option, but also
        # modified by `--insert`, and entries may be modified as well. Note that we do not process
        # step data here, this list is not the input we iterate over - we process CLI invocations,
        # and based on their content we modify this list and its content.
        raw_data: List[_RawStepData] = self._raw_data[:]

        # Some invocations cannot be easily evaluated when we first spot them. To remain backward
        # compatible, `--update` without `--name` should result in all phases being converted into
        # what the `--update` brings in. In this list, we will collect "postponed" CLI invocations,
        # and we will get back to them once we're done with those we can apply immediately.
        postponed_invocations: List['tmt.cli.CliInvocation'] = []

        name_generator = DefaultNameGenerator.from_raw_phases(raw_data)

        def _ensure_name(raw_datum: _RawStepData) -> _RawStepData:
            """ Make sure a phase specification does have a name """

            if not raw_datum.get('name'):
                raw_datum['name'] = name_generator.get()

            return raw_datum

        def _patch_raw_datum(
                raw_datum: _RawStepData,
                incoming_raw_datum: _RawStepData,
                invocation: 'tmt.cli.CliInvocation',
                missing_only: bool = False) -> None:
            """
            Copy options from one phase specification onto another.

            Serves as a helper for "patching" a phase with options coming from
            a command line. It must avoid copying options that were not really
            given by user - because of how options are handled, simple
            ``dict.update()`` would not do as ``incoming_raw_datum`` would
            contain **all** options as long as they have a default value.

            Click is therefore consulted for each key/option, whether it was
            really specified on the command line (or by an environment
            variable).
            """

            local_debug = functools.partial(debug, shift=1)

            local_debug('raw step datum', str(raw_datum))
            local_debug('incoming raw step datum', str(incoming_raw_datum))
            local_debug('CLI invocation', str(invocation.options))

            for opt, value in incoming_raw_datum.items():
                if opt == 'name':
                    continue

                key = option_to_key(opt)
                value_source = invocation.option_sources.get(key)

                local_debug(f'{opt=} {key=} {value=} {value_source=}')

                # Ignore CLI input if it's been provided by option's default
                if value_source not in (ParameterSource.COMMANDLINE, ParameterSource.ENVIRONMENT):
                    debug('value not really given via CLI/env, no effect', shift=2)
                    continue

                if missing_only and opt in raw_datum:
                    debug('missing-only mode and key exists in raw datum, no effect', shift=2)
                    continue

                # ignore[literal-required]: since raw_datum is a typed dict,
                # mypy allows only know keys to be set & enforces use of
                # literals as keys. Use of a variable is frowned upon and
                # reported - but we define only the very basic keys in
                # `_RawStepData` and we do expect there are keys we do not
                # care about, keys that make sense to whatever plugin is
                # materialized from the raw step data.
                debug('apply invocation value', shift=2)
                raw_datum[opt] = value  # type: ignore[literal-required]

        # A bit of logging before we start messing with step data
        for i, raw_datum in enumerate(raw_data):
            debug(f'raw step datum #{i}', str(raw_datum))

        # The first pass, apply CLI invocations that can be applied
        for i, invocation in enumerate(self.__class__.cli_invocations):
            debug(f'invocation #{i}', str(invocation.options))

            how: Optional[str] = invocation.options.get('how')

            if how is None:
                debug('  how-less phase (postponed)')

                postponed_invocations.append(invocation)

            elif invocation.options.get('insert'):
                debug('  inserting new phase')

                raw_datum = _to_raw_step_datum(invocation.options)
                raw_datum = _ensure_name(raw_datum)

                raw_data.append(raw_datum)

            elif invocation.options.get('update'):
                debug('  updating existing phase')

                needle = invocation.options.get('name')

                if needle:
                    incoming_raw_datum = _to_raw_step_datum(invocation.options)

                    for raw_datum in raw_data:
                        if raw_datum['name'] != needle:
                            continue

                        _patch_raw_datum(raw_datum, incoming_raw_datum, invocation)

                        break

                    else:
                        raise GeneralError(
                            f"Cannot update phase '{needle}', no such name was found.")

                else:
                    debug('  needle-less update (postponed)')

                    postponed_invocations.append(invocation)

            elif invocation.options.get('update_missing'):
                debug('  updating existing phase (missing fields only)')

                needle = invocation.options.get('name')

                if needle:
                    incoming_raw_datum = _to_raw_step_datum(invocation.options)

                    for raw_datum in raw_data:
                        if raw_datum['name'] != needle:
                            continue

                        _patch_raw_datum(
                            raw_datum,
                            incoming_raw_datum,
                            invocation,
                            missing_only=True)

                        break

                    else:
                        raise GeneralError(
                            f"Cannot update phase '{needle}', no such name was found.")

                else:
                    debug('  needle-less update (postponed)')

                    postponed_invocations.append(invocation)

            else:
                debug('  action-less phase (postponed)')

                postponed_invocations.append(invocation)

        # The second pass, evaluate postponed CLI invocations
        for i, invocation in enumerate(postponed_invocations):
            debug(f'postponed invocation #{i}', str(invocation.options))

            pruned_raw_data: List[_RawStepData] = []
            incoming_raw_datum = _to_raw_step_datum(invocation.options)

            how = invocation.options['how']

            for j, raw_datum in enumerate(raw_data):
                debug(f'raw step datum #{j}', str(raw_datum))

                if how is None:
                    debug('  compatible step data (how-less invocation)')

                elif raw_datum['how'] == how:
                    debug('  compatible step data')

                else:
                    debug('  incompatible step data')

                    raw_datum = {
                        'name': raw_datum['name'],
                        'how': how
                        }

                if invocation.options.get('update_missing'):
                    _patch_raw_datum(raw_datum, incoming_raw_datum, invocation, missing_only=True)

                else:
                    _patch_raw_datum(raw_datum, incoming_raw_datum, invocation)

                pruned_raw_data.append(raw_datum)

            raw_data = pruned_raw_data

        # And bit of logging after re're done with CLI invocations
        for i, raw_datum in enumerate(raw_data):
            debug(f'updated raw step datum #{i}', str(raw_datum))

        self._set_default_values(raw_data)
        self.data = self._normalize_data(raw_data, self._logger)
        self._raw_data = raw_data

        # A final bit of logging, to record what we ended up with after all inputs and fixups were
        # applied.
        for i, datum in enumerate(self.data):
            debug(f'final step data #{i}', str(datum))

    def setup_actions(self) -> None:
        """ Insert login and reboot plugins if requested """
        for login_plugin in Login.plugins(step=self):
            self.debug(
                f"Insert a login plugin into the '{self}' step "
                f"with order '{login_plugin.order}'.", level=2)
            self._phases.append(login_plugin)

        for reboot_plugin in Reboot.plugins(step=self):
            self.debug(
                f"Insert a reboot plugin into the '{self}' step "
                f"with order '{reboot_plugin.order}'.", level=2)
            self._phases.append(reboot_plugin)

    @overload
    def phases(self, classes: None = None) -> List[Phase]:
        pass

    @overload
    def phases(self, classes: Type[PhaseT]) -> List[PhaseT]:
        pass

    @overload
    def phases(self, classes: Tuple[Type[PhaseT], ...]) -> List[PhaseT]:
        pass

    def phases(self, classes: Optional[Union[Type[PhaseT],
               Tuple[Type[PhaseT], ...]]] = None) -> List[PhaseT]:
        """
        Iterate over phases by their order

        By default iterates over all available phases. Optional filter
        'classes' can be used to iterate only over instances of given
        class (single class or tuple of classes).
        """

        if classes is None:
            _classes: Tuple[Union[Type[Phase], Type[PhaseT]], ...] = (Phase,)

        elif not isinstance(classes, tuple):
            _classes = (classes,)

        else:
            _classes = classes

        return sorted(
            [cast(PhaseT, phase) for phase in self._phases if isinstance(phase, _classes)],
            key=lambda phase: phase.order)

    def actions(self) -> None:
        """ Run all loaded Login or Reboot action instances of the step """
        for phase in self.phases(classes=Action):
            phase.go()

    def go(self) -> None:
        """ Execute the test step """
        # Show step header and how
        self.info(self.name, color='blue')
        # Show workdir in verbose mode
        if self.workdir:
            self.debug('workdir', self.workdir, 'magenta')

    def prune(self, logger: tmt.log.Logger) -> None:
        """ Remove all uninteresting files from the step workdir """
        if self.workdir is None:
            return

        logger.debug(f"Prune '{self.name}' step workdir '{self.workdir}'.", level=3)
        logger = logger.descend()

        # Collect all workdir members that shall not be removed
        preserved_members: List[str] = self._preserved_workdir_members[:]

        # Do not prune plugin workdirs, each plugin decides what should
        # be pruned from the workdir and what should be kept there
        plugins = self.phases(classes=BasePlugin)
        for plugin in plugins:
            if plugin.workdir is not None:
                preserved_members.append(plugin.workdir.name)
            plugin.prune(logger)

        # Prune everything except for the preserved files
        for member in self.workdir.iterdir():
            if member.name in preserved_members:
                logger.debug(f"Preserve '{member.relative_to(self.workdir)}'.", level=3)
                continue
            logger.debug(f"Remove '{member}'.", level=3)
            try:
                if member.is_file() or member.is_symlink():
                    member.unlink()
                else:
                    shutil.rmtree(member)
            except OSError as error:
                logger.warn(f"Unable to remove '{member}': {error}")

    def requires(self) -> List['tmt.base.Dependency']:
        """
        Collect all requirements of all enabled plugins in this step.

        Puts together a list of requirements which need to be installed on the
        provisioned guest so that all enabled plugins of this step can be
        successfully executed.

        :returns: a list of requirements, with duplicaties removed.
        """
        return flatten(
            (plugin.requires() for plugin in self.phases(classes=self._plugin_base_class)),
            unique=True
            )


class Method:
    """ Step implementation method """

    def __init__(
            self,
            name: str,
            class_: Optional[PluginClass] = None,
            doc: Optional[str] = None,
            order: int = DEFAULT_PLUGIN_METHOD_ORDER
            ) -> None:
        """ Store method data """

        doc = (doc or class_.__doc__ or '').strip()

        if not doc:
            if class_:
                raise tmt.utils.GeneralError(f"Plugin class '{class_}' provides no docstring.")

            raise tmt.utils.GeneralError(f"Plugin method '{name}' provides no docstring.")

        self.name = name
        self.class_ = class_
        self.doc = doc
        self.order = order

        # Parse summary and description from provided doc string
        lines: List[str] = [re.sub('^    ', '', line)
                            for line in self.doc.split('\n')]
        self.summary: str = lines[0].strip()
        self.description: str = '\n'.join(lines[1:]).lstrip()

    def describe(self) -> str:
        """ Format name and summary for a nice method overview """
        return f'{self.name} '.ljust(22, '.') + f' {self.summary}'

    def usage(self) -> str:
        """ Prepare a detailed usage from summary and description """
        if self.description:
            usage: str = self.summary + '\n\n' + self.description
        else:
            usage = self.summary
        # Disable wrapping for all paragraphs
        return re.sub('\n\n', '\n\n\b\n', usage)


def provides_method(
        name: str,
        doc: Optional[str] = None,
        order: int = DEFAULT_PLUGIN_METHOD_ORDER) -> Callable[[PluginClass], PluginClass]:
    """
    A plugin class decorator to register plugin's method with tmt steps.

    In the following example, developer marks ``SomePlugin`` as providing two discover methods,
    ``foo`` and ``bar``, with ``bar`` being sorted to later position among methods:

    .. code-block:: python

       @tmt.steps.provides_method('foo')
       @tmt.steps.provides_method('bar', order=80)
       class SomePlugin(tmt.steps.discover.DicoverPlugin):
         ...

    :param name: name of the method.
    :param doc: method documentation. If not specified, docstring of the decorated class is used.
    :param order: order of the method among other step methods.
    """

    def _method(cls: PluginClass) -> PluginClass:
        plugin_method = Method(name, class_=cls, doc=doc, order=order)

        # FIXME: make sure cls.__bases__[0] is really BasePlugin class
        cast('BasePlugin', cls.__bases__[0])._supported_methods \
            .register_plugin(
                plugin_id=name,
                plugin=plugin_method,
                logger=tmt.log.Logger.get_bootstrap_logger())

        return cls

    return _method


class BasePlugin(Phase):
    """ Common parent of all step plugins """

    # Deprecated, use @provides_method(...) instead. left for backward
    # compatibility with out-of-tree plugins.
    _methods: List[Method] = []

    # Default implementation for all steps is shell
    # except for provision (virtual) and report (display)
    how: str = 'shell'

    # Methods ("how: ..." implementations) registered for the same step.
    #
    # The field is declared here, in a base class of all plugin classes, and
    # each step-specific base plugin class assignes it a value as a class-level
    # attribute. This guarantees steps would not share a registry instance while
    # the declaration below make the name and type visible across all
    # subclasses.
    _supported_methods: 'tmt.plugins.PluginRegistry[Method]'

    _data_class: Type[StepData] = StepData
    data: StepData

    # TODO: do we need this list? Can whatever code is using it use _data_class directly?
    # List of supported keys
    # (used for import/export to/from attributes during load and save)
    @property
    def _keys(self) -> List[str]:
        return list(self._data_class.keys())

    def __init__(
            self,
            *,
            step: Step,
            data: StepData,
            workdir: tmt.utils.WorkdirArgumentType = None,
            logger: tmt.log.Logger) -> None:
        """ Store plugin name, data and parent step """
        logger.apply_verbosity_options(cli_invocation=self.__class__.cli_invocation)

        # Store name, data and parent step
        super().__init__(
            logger=logger,
            parent=step,
            name=data.name,
            workdir=workdir,
            order=data.order)

        # It is not possible to use TypedDict here because
        # all keys are not known at the time of the class definition
        self.data = data
        self.step = step

    @cached_property
    def safe_name(self) -> str:
        """
        A safe variant of the name which does not contain special characters.

        Override parent implementation as we do not allow phase names to contain
        slash characters, ``/``.
        """

        return tmt.utils.sanitize_name(self.name, allow_slash=False)

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[Type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all step plugins) """
        raise NotImplementedError

    @classmethod
    def options(cls, how: Optional[str] = None) -> List[tmt.options.ClickOptionDecoratorType]:
        """ Prepare command line options for given method """
        # Include common options supported across all plugins
        return [
            metadata.option
            for metadata in (
                tmt.utils.dataclass_field_metadata(field)
                for field in dataclasses.fields(cls._data_class)
                )
            if metadata.option is not None
            ] + tmt.options.VERBOSITY_OPTIONS + tmt.options.FORCE_DRY_OPTIONS

    @classmethod
    def command(cls) -> click.Command:
        """ Prepare click command for all supported methods """
        # Create one command for each supported method
        commands: Dict[str, click.Command] = {}
        method_overview: str = f'Supported methods ({cls.how} by default):\n\n\b'
        for method in cls.methods():
            assert method.class_ is not None
            method_overview += f'\n{method.describe()}'
            command: click.Command = cls.base_command(usage=method.usage())
            # Apply plugin specific options
            for method_option in method.class_.options(method.name):
                command = method_option(command)
            commands[method.name] = command

            for param in command.params:
                if param.name == 'how':
                    continue

                if not isinstance(param, click.Option):
                    continue

                assert command.name is not None  # narrow type
                assert param.name is not None  # narrow type

                command_name, method_name, param_name = \
                    command.name.upper(), method.name.upper(), param.name.upper()

                envvar = f'TMT_PLUGIN_{command_name}_{method_name}_{param_name}'

                # We do not want to overwrite existing envvar setup of the parameter,
                # we want to *add* our variable. The `envvar` attribute can be of
                # different types, carefully modify each variant:

                # Unset...
                if param.envvar is None:
                    param.envvar = [envvar]

                # ..., a string, i.e. a single pre-set envvar, ...
                elif isinstance(param.envvar, str):
                    param.envvar = [param.envvar, envvar]

                # ..., a list of strings, i.e. several pre-set envvars, or...
                elif isinstance(param.envvar, list):
                    param.envvar.append(envvar)

                # ... or an unexpected type we don't know how to handle.
                else:
                    raise tmt.utils.GeneralError(
                        f"Envvar property of '{param.name}' option "
                        f"set to unexpected type '{type(param.envvar)}'.")

        # Create base command with common options using method class
        method_class = tmt.options.create_method_class(commands)
        command = cls.base_command(usage=method_overview, method_class=method_class)
        # Apply common options
        for common_option in cls.options():
            command = common_option(command)
        return command

    @classmethod
    def methods(cls) -> List[Method]:
        """ Return all supported methods ordered by priority """
        return sorted(cls._supported_methods.iter_plugins(), key=lambda method: method.order)

    @classmethod
    def delegate(
            cls,
            step: Step,
            data: Optional[StepData] = None,
            raw_data: Optional[_RawStepData] = None) -> 'BasePlugin':
        """
        Return plugin instance implementing the data['how'] method

        Supports searching by method prefix as well (e.g. 'virtual').
        The first matching method with the lowest 'order' wins.
        """

        if data is not None:
            how = data.how
        elif raw_data is not None:
            how = raw_data['how']
        else:
            raise tmt.utils.GeneralError('Either data or raw data must be given.')

        step.debug(
            f'{cls.__name__}.delegate(step={step}, data={data}, raw_data={raw_data})',
            level=3)

        # Filter matching methods, pick the one with the lowest order
        for method in cls.methods():
            assert method.class_ is not None
            if method.name.startswith(how):
                step.debug(
                    f"Using the '{method.class_.__name__}' plugin "
                    f"for the '{how}' method.", level=2)

                plugin_class = method.class_
                plugin_data_class = plugin_class._data_class

                # If we're given raw data, construct a step data instance, applying
                # normalization in the process.
                if raw_data is not None:
                    try:
                        data = plugin_data_class.from_spec(raw_data, step._logger)

                    except Exception as exc:
                        raise tmt.utils.GeneralError(
                            f'Failed to load step data for {plugin_data_class.__name__}: {exc}') \
                            from exc

                assert data is not None
                assert data.__class__ is plugin_data_class, \
                    f'Data package is instance of {data.__class__.__name__}, ' \
                    f'plugin {plugin_class.__name__} ' \
                    f'expects {plugin_data_class.__name__}'

                plugin = plugin_class(
                    logger=step._logger.descend(logger_name=None),
                    step=step,
                    data=data
                    )
                assert isinstance(plugin, BasePlugin)
                return plugin

        show_step_method_hints(step.name, how, step._logger)
        # Report invalid method
        if step.plan is None:
            raise tmt.utils.GeneralError(f"Plan for {step.name} is not set.")
        raise tmt.utils.SpecificationError(
            f"Unsupported {step.name} method '{how}' "
            f"in the '{step.plan.name}' plan.")

    def default(self, option: str, default: Optional[Any] = None) -> Any:
        """ Return default data for given option """

        value = self._data_class.default(tmt.utils.option_to_key(option), default=default)

        if value is None:
            return default

        return value

    def get(self, option: str, default: Optional[Any] = None) -> Any:
        """ Get option from plugin data, user/system config or defaults """

        # Check plugin data first
        #
        # Since self.data is a dataclass instance, the option would probably exist.
        # As long as there's no typo in name, it would be defined. Which complicates
        # the handling of "default" as in "return *this* when attribute is unset".
        key = tmt.utils.option_to_key(option)

        try:
            value = getattr(self.data, key)

            # If the value is no longer the default one, return the value. If it
            # still matches the default value, instead of returning the default
            # value right away, call `self.default()` so the plugin has chance to
            # catch calls for computed or virtual keys, keys that don't exist as
            # atributes of our step data.
            #
            # One way would be to subclass step's base plugin class' step data class
            # (which is a subclass of `StepData` and `SerializedContainer`), and
            # override its `default()` method to handle these keys. But, plugins often
            # are pretty happy with the base data class, many don't need their own
            # step data class, and plugin developer might be forced to create a subclass
            # just for this single method override.
            #
            # Instead, keep plugin's `default()` around - everyone can use it to get
            # default value for a given option/key, and plugins can override it as needed
            # (they will always subclass step's base plugin class anyway!). Default
            # implementation would delegate to step data `default()`, and everyone's
            # happy.

            if value != self.data.default(key):
                return value

        except AttributeError:
            pass

        return self.default(option, default)

    def show(self, keys: Optional[List[str]] = None) -> None:
        """ Show plugin details for given or all available keys """
        # Avoid circular imports
        import tmt.base

        # Show empty config with default method only in verbose mode
        if self.data.is_bare and not self.verbosity_level:
            return
        # Step name (and optional summary)
        echo(tmt.utils.format(
            self.step.name, self.get('summary') or '',
            key_color='blue', value_color='blue'))
        # Show all or requested step attributes
        if keys is None:
            keys = list(set(self.data.keys()))

        def _emit_key(key: str) -> None:
            # Skip showing the default name
            if key == 'name' and self.name.startswith(tmt.utils.DEFAULT_NAME):
                return

            # Skip showing summary again
            if key == 'summary':
                return

            # TODO: this field belongs to provision, but does it even make sense
            # to *show* this field? When a plan is shown, there is no guest to
            # speak about, nothing is provisioned...
            if key == 'facts':
                return

            value = self.get(key)

            # No need to show the default order
            if key == 'order' and value == tmt.base.DEFAULT_ORDER:
                return

            if value is None:
                return

            # TODO: we will have `internal` and better filtering to not spill
            # internal fields. For now, a condition will do.
            if key.startswith('_'):
                return

            # TODO: hides keys that were used to be in the output...
            # if value == self.data.default(key):
            #     return

            echo(tmt.utils.format(tmt.utils.key_to_option(key), value))

        # First, follow the order prefered by step data, but emit only the keys
        # that are allowed. Each emitted key would be removed so we wouldn't
        # emit it again when showing the unsorted rest of keys.
        for key in self.data._KEYS_SHOW_ORDER:
            if key not in keys:
                continue

            _emit_key(key)

            keys.remove(key)

        # Show the rest
        for key in keys:
            _emit_key(key)

    def enabled_on_guest(self, guest: 'Guest') -> bool:
        """ Check if the plugin is enabled on the specific guest """

        # FIXME: cast() - typeless "dispatcher" method
        where = cast(List[str], self.get('where'))

        if not where:
            return True

        return any(destination in (guest.name, guest.role) for destination in where)

    def wake(self) -> None:
        """
        Wake up the plugin, process data, apply options

        Check command line options corresponding to plugin keys
        and store their value into the 'self.data' dictionary if
        their value is True or non-empty.

        By default, all supported options corresponding to common
        and plugin-specific keys are processed. List of key names
        in the 'keys' parameter can be used to override only
        selected ones.
        """

        assert self.data.__class__ is self._data_class, \
            f'Plugin {self.__class__.__name__} woken with incompatible ' \
            f'data {self.data}, ' \
            f'expects {self._data_class.__name__}'

        if self.step.status() == 'done':
            self.debug('step is done, not overwriting plugin data')
            return

        # TODO: conflicts with `upgrade` plugin which does this on purpose :/
        # if self.opt('how') is not None:
        #     assert self.opt('how') in [method.name for method in self.methods()], \
        #         f'Plugin {self.__class__.__name__} woken with unsupported ' \
        #         f'how "{self.opt("how")}", ' \
        #         f'supported methods {", ".join([method.name for method in self.methods()])}, ' \
        #         f'current data is {self.data}'

    # NOTE: it's tempting to rename this method to `go()` and use more natural
    # `super().go()` in child classes' `go()` methods. But, `go()` does not have
    # the same signature across all plugin types, therefore we cannot have shared
    # `go()` method in superclass - overriding it in (some) child classes would
    # raise a typing linter error reporting superclass signature differs from the
    # one in a subclass.
    #
    # Therefore we need a different name, and a way how not to forget to call this
    # method from child classes.
    def go_prolog(self, logger: tmt.log.Logger) -> None:
        """ Perform actions shared among plugins when beginning their tasks """

        logger = logger or self._logger

        # Show the method
        logger.info('how', self.get('how'), 'magenta')
        # Give summary if provided
        if self.get('summary'):
            logger.info('summary', self.get('summary'), 'magenta')
        # Show name only if it's not the default one
        if not self.name.startswith(tmt.utils.DEFAULT_NAME):
            logger.info('name', self.name, 'magenta')
        # Include order in verbose mode
        logger.verbose('order', self.order, 'magenta', level=3)

    def requires(self) -> List['tmt.base.Dependency']:
        """ All requirements of the plugin on the guest """
        return []

    def prune(self, logger: tmt.log.Logger) -> None:
        """
        Prune uninteresting files from the plugin workdir

        By default we remove the whole workdir. Individual plugins can
        override this method to keep files and directories which are
        useful for inspection when the run is finished.
        """
        if self.workdir is None:
            return
        logger.debug(f"Remove '{self.name}' workdir '{self.workdir}'.", level=3)
        try:
            shutil.rmtree(self.workdir)
        except OSError as error:
            logger.warn(f"Unable to remove '{self.workdir}': {error}")


class GuestlessPlugin(BasePlugin):
    """ Common parent of all step plugins that do not work against a particular guest """

    def go(self) -> None:
        """ Perform actions shared among plugins when beginning their tasks """

        self.go_prolog(self._logger)


class Plugin(BasePlugin):
    """ Common parent of all step plugins that do work against a particular guest """

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Perform actions shared among plugins when beginning their tasks """

        self.go_prolog(logger)


class Action(Phase, tmt.utils.MultiInvokableCommon):
    """ A special action performed during a normal step. """

    # Dictionary containing list of requested phases for each enabled step
    _phases: Optional[Dict[str, List[int]]] = None

    @classmethod
    def phases(cls, step: Step) -> List[int]:
        """ Return list of phases enabled for given step """
        # Build the phase list unless done before
        if cls._phases is None:
            cls._phases = cls._parse_phases(step)
        # Return enabled phases, empty list if step not found
        try:
            return cls._phases[step.name]
        except KeyError:
            return []

    @classmethod
    def _parse_phases(cls, step: Step) -> Dict[str, List[int]]:
        """ Parse options and store phase order """
        phases = {}
        options: List[str] = cls._opt('step', default=[])

        # Use the end of the last enabled step if no --step given
        if not options:
            login_during: Optional[Step] = None
            # The last run may have failed before all enabled steps were
            # completed, select the last step done
            if step.plan is None:
                raise tmt.utils.GeneralError(
                    f"Plan for {step.name} is not set.")
            assert step.plan.my_run is not None  # narrow type
            if step.plan.my_run.opt('last'):
                steps: List[Step] = [
                    s for s in step.plan.steps() if s.status() == 'done']
                login_during = steps[-1] if steps else None
            # Default to the last enabled step if no completed step found
            if login_during is None:
                login_during = list(step.plan.steps())[-1]
            # Only login if the error occurred after provision
            if login_during != step.plan.discover:
                phases[login_during.name] = [PHASE_END]

        # Process provided options
        for step_option in options:
            # Parse the step:phase format
            matched = re.match(r'(\w+)(:(\w+))?', step_option)
            if matched:
                step_name, _, phase = matched.groups()
            if not matched or step_name not in STEPS:
                raise tmt.utils.GeneralError(f"Invalid step '{step_option}'.")
            # Check phase format, convert into int, use end by default
            try:
                phase = int(phase)
            except TypeError:
                phase = PHASE_END
            except ValueError:
                # Convert 'start' and 'end' aliases
                try:
                    phase = cast(Dict[str, int],
                                 {'start': PHASE_START, 'end': PHASE_END})[phase]
                except KeyError:
                    raise tmt.utils.GeneralError(f"Invalid phase '{phase}'.")
            # Store the phase for given step
            try:
                phases[step_name].append(phase)
            except KeyError:
                phases[step_name] = [phase]
        return phases

    def go(self) -> None:
        raise NotImplementedError


class Reboot(Action):
    """ Reboot guest """

    # True if reboot enabled
    _enabled: bool = False

    def __init__(self, *, step: Step, order: int, logger: tmt.log.Logger) -> None:
        """ Initialize relations, store the reboot order """
        super().__init__(logger=logger, parent=step, name='reboot', order=order)

    @classmethod
    def command(
            cls,
            method_class: Optional[Method] = None,
            usage: Optional[str] = None) -> click.Command:
        """ Create the reboot command """
        @click.command()
        @click.pass_context
        @option(
            '-s', '--step', metavar='STEP[:PHASE]', multiple=True,
            help='Reboot machine during given phase of selected step(s).')
        @option(
            '--hard', is_flag=True,
            help='Hard reboot of the machine. Unsaved data may be lost.')
        def reboot(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            """ Reboot the guest. """
            Reboot.store_cli_invocation(context)
            Reboot._enabled = True

        return reboot

    @classmethod
    def plugins(cls, step: Step) -> List['Reboot']:
        """ Return list of reboot instances for given step """
        if not Reboot._enabled:
            return []
        return [Reboot(logger=step._logger.descend(), step=step, order=phase)
                for phase in cls.phases(step)]

    def go(self) -> None:
        """ Reboot the guest(s) """
        self.info('reboot', 'Rebooting guest', color='yellow')
        assert isinstance(self.parent, Step)
        assert hasattr(self.parent, 'plan')
        assert self.parent.plan is not None
        for guest in self.parent.plan.provision.guests():
            guest.reboot(hard=self.opt('hard'))
        self.info('reboot', 'Reboot finished', color='yellow')


class Login(Action):
    """ Log into the guest """

    # TODO: remove when Step becomes Generic (#1372)
    # Change typing of inherited attr
    parent: Step

    # True if interactive login enabled
    _enabled: bool = False

    def __init__(self, *, step: Step, order: int, logger: tmt.log.Logger) -> None:
        """ Initialize relations, store the login order """
        super().__init__(logger=logger, parent=step, name='login', order=order)

    @classmethod
    def command(
            cls,
            method_class: Optional[Method] = None,
            usage: Optional[str] = None) -> click.Command:
        """ Create the login command """
        # Avoid circular imports
        from tmt.result import ResultOutcome

        @click.command()
        @click.pass_context
        @option(
            '-s', '--step', metavar='STEP[:PHASE]', multiple=True,
            help='Log in during given phase of selected step(s).')
        @option(
            '-w', '--when', metavar='RESULT', multiple=True,
            choices=[m.value for m in ResultOutcome.__members__.values()],
            help='Log in if a test finished with given result(s).')
        @option(
            '-c', '--command', metavar='COMMAND',
            multiple=True, default=['bash'],
            help="Run given command(s). Default is 'bash'.")
        @option(
            '-t', '--test', is_flag=True,
            help='Log into the guest after each executed test in the execute phase.')
        def login(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            """
            Provide user with an interactive shell on the guest.

            By default the shell is provided at the end of the last
            enabled step. When used together with the --last option the
            last completed step is selected. Use one or more --step
            options to select a different step instead.

            Optional phase can be provided to specify the exact phase of
            the step when the shell should be provided. The following
            values are supported:

            \b
                start ... beginning of the step (same as '10')
                end ..... end of the step (default, same as '90')
                00-99 ... integer order defining the exact phase

            Usually the main step execution happens with order 50.
            Consult individual step documentation for more details.

            For the execute step and following steps it is also possible
            to conditionally enable the login feature only if some of
            the tests finished with given result (pass, info, fail,
            warn, error).
            """
            Login.store_cli_invocation(context)
            Login._enabled = True

        return login

    @classmethod
    def plugins(cls, step: Step) -> List['Login']:
        """ Return list of login instances for given step """
        if not Login._enabled:
            return []
        return [Login(logger=step._logger.descend(), step=step, order=phase)
                for phase in cls.phases(step)]

    def go(self) -> None:
        """ Login to the guest(s) """

        if self._enabled_by_results(self.parent.plan.execute.results()):
            self._login()

    def _enabled_by_results(self, results: List['tmt.base.Result']) -> bool:
        """ Verify possible test result condition """
        # Avoid circular imports
        from tmt.result import ResultOutcome
        expected_results: Optional[List[ResultOutcome]] = [ResultOutcome.from_spec(
            raw_expected_result) for raw_expected_result in self.opt('when', [])]

        # Return True by default -> no expected results
        if not expected_results:
            return True

        # Check for expected result
        for result in results:
            if result.result in expected_results:
                return True
        else:  # No break/return in for cycle
            self.info('Skipping interactive shell', color='yellow')
            return False

    def _login(
            self,
            cwd: Optional[Path] = None,
            env: Optional[tmt.utils.EnvironmentType] = None) -> None:
        """ Run the interactive command """
        scripts = [tmt.utils.ShellScript(script) for script in self.opt('command')]
        self.info('login', 'Starting interactive shell', color='yellow')
        for guest in self.parent.plan.provision.guests():
            # Attempt to push the workdir to the guest
            try:
                guest.push()
                cwd = cwd or self.parent.plan.worktree
            except tmt.utils.GeneralError:
                self.warn("Failed to push workdir to the guest.")
                cwd = None
            # Execute all requested commands
            for script in scripts:
                self.debug(f"Run '{script}' in interactive mode.")
                guest.execute(script, interactive=True, cwd=cwd, env=env)
        self.info('login', 'Interactive shell finished', color='yellow')

    def after_test(
            self,
            result: 'tmt.base.Result',
            cwd: Optional[Path] = None,
            env: Optional[tmt.utils.EnvironmentType] = None) -> None:
        """ Check and login after test execution """
        if self._enabled_by_results([result]):
            self._login(cwd, env)


@dataclasses.dataclass
class GuestTopology(tmt.utils.SerializableContainer):
    """ Describes a guest in the topology of provisioned tmt guests """

    name: str
    role: Optional[str]
    hostname: Optional[str]

    def __init__(self, guest: 'Guest') -> None:
        self.name = guest.name
        self.role = guest.role
        self.hostname = guest.guest


@dataclasses.dataclass(init=False)
class Topology(tmt.utils.SerializableContainer):
    """ Describes the topology of provisioned tmt guests """

    guest: Optional[GuestTopology]

    guest_names: List[str]
    guests: Dict[str, GuestTopology]

    role_names: List[str]
    roles: Dict[str, List[str]]

    def __init__(self, guests: List['Guest']) -> None:
        roles: DefaultDict[str, List['Guest']] = collections.defaultdict(list)

        self.guest = None
        self.guest_names: List[str] = []
        self.guests = {}

        for guest in guests:
            self.guest_names.append(guest.name)

            self.guests[guest.name] = GuestTopology(guest)

            if guest.role:
                roles[guest.role].append(guest)

        self.role_names = list(roles.keys())
        self.roles = {
            role: [guest.name for guest in role_guests]
            for role, role_guests in roles.items()
            }

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to a mapping.

        See https://tmt.readthedocs.io/en/stable/classes.html#class-conversions for more details.
        """

        data = super().to_dict()

        data['guest'] = self.guest.to_dict() if self.guest else None
        data['guests'] = {
            guest_name: guest.to_dict() for guest_name, guest in self.guests.items()

            }

        return data

    def save_yaml(self, dirpath: Path, filename: Optional[str] = None) -> Path:
        """
        Save the topology in a YAML file.

        :param dirpath: a directory to save into.
        :param filename: if set, it would be used, otherwise a filename is
            created from :py:const:`TEST_TOPOLOGY_FILENAME_BASE` and ``.yaml``
            suffix.
        :returns: path to the saved file.
        """

        filename = filename or f'{TEST_TOPOLOGY_FILENAME_BASE}.yaml'
        filepath = dirpath / filename

        serialized = self.to_dict()

        # Stick to using `-` for multiword keys.
        # TODO: after https://github.com/teemtee/tmt/pull/2095/, this could
        # be handled by SerializableContainer transparently.
        serialized['guest-names'] = serialized.pop('guest_names')
        serialized['role-names'] = serialized.pop('role_names')

        filepath.write_text(tmt.utils.dict_to_yaml(serialized))

        return filepath

    def save_bash(self, dirpath: Path, filename: Optional[str] = None) -> Path:
        """
        Save the topology in a Bash-sourceable file.

        :param dirpath: a directory to save into.
        :param filename: if set, it would be used, otherwise a filename is
            created from :py:const:`TEST_TOPOLOGY_FILENAME_BASE` and ``.sh``
            suffix.
        :returns: path to the saved file.
        """

        filename = filename or f'{TEST_TOPOLOGY_FILENAME_BASE}.sh'
        filepath = dirpath / filename

        lines: List[str] = []

        def _emit_guest(guest: GuestTopology, variable: str,
                        key: Optional[str] = None) -> List[str]:
            return [
                f'{variable}[{key or ""}name]="{guest.name}"',
                f'{variable}[{key or ""}role]="{guest.role or ""}"',
                f'{variable}[{key or ""}hostname]="{guest.hostname or ""}"'
                ]

        if self.guest:
            lines += [
                'declare -A TMT_GUEST',
                *_emit_guest(self.guest, 'TMT_GUEST'),
                ''
                ]

        lines += [
            f'TMT_GUEST_NAMES="{" ".join(self.guest_names)}"',
            '',
            'declare -A TMT_GUESTS'
            ]

        for guest_info in self.guests.values():
            lines += _emit_guest(guest_info, 'TMT_GUESTS', key=f'{guest_info.name}.')

        lines += [
            '',
            f'TMT_ROLE_NAMES="{" ".join(self.role_names)}"',
            '',
            'declare -A TMT_ROLES'
            ]

        for role, guest_names in self.roles.items():
            lines += [
                f'TMT_ROLES[{role}]="{" ".join(guest_names)}"'
                ]

        filepath.write_text("\n".join(lines))

        return filepath

    def save(
            self,
            *,
            dirpath: Path,
            filename_base: Optional[str] = None) -> List[Path]:
        """
        Save the topology in files.

        :param dirpath: a directory to save into.
        :param filename_base: if set, it would be used as a base for filenames,
            correct suffixes would be added.
        :returns: list of paths to saved files.
        """

        return [
            self.save_yaml(dirpath, filename=(f'{filename_base}.yaml' if filename_base else None)),
            self.save_bash(dirpath, filename=(f'{filename_base}.sh' if filename_base else None))
            ]

    def push(
            self,
            *,
            dirpath: Path,
            guest: 'Guest',
            filename_base: Optional[str] = None,
            logger: tmt.log.Logger) -> EnvironmentType:
        """
        Save and push topology to a given guest.
        """

        topology_filepaths = self.save(dirpath=dirpath, filename_base=filename_base)

        environment: EnvironmentType = {}

        for filepath in topology_filepaths:
            logger.debug('test topology', filepath)

            guest.push(
                source=filepath,
                destination=filepath,
                options=["-s", "-p", "--chmod=755"])

            if filepath.suffix == '.sh':
                environment['TMT_TOPOLOGY_BASH'] = str(filepath)

            elif filepath.suffix == '.yaml':
                environment['TMT_TOPOLOGY_YAML'] = str(filepath)

            else:
                raise tmt.utils.GeneralError(f"Unhandled topology file '{filepath}'.")

        return environment


@dataclasses.dataclass
class QueuedPhase(GuestlessTask, Task):
    """ A phase to run on one or more guests """

    phase: Union[Action, Plugin]

    # A cached environment, it will be initialized by `prepare_environment()`
    # on the first call.
    _environment: Optional[EnvironmentType] = None

    @property
    def phase_name(self) -> str:
        from tmt.steps.execute import ExecutePlugin

        # A better fitting name for an execute step phase, instead of its own
        # name, which is always the same, would be the name of the discover
        # phase it's supposed to process.
        if isinstance(self.phase, ExecutePlugin):
            return self.phase.discover_phase or self.phase.discover.name

        return self.phase.name

    @property
    def name(self) -> str:
        return self.phase_name

    def run(self, logger: tmt.log.Logger) -> None:
        assert isinstance(self.phase, Action)  # narrow type

        self.phase.go()

    def run_on_guest(self, guest: 'Guest', logger: tmt.log.Logger) -> None:
        assert isinstance(self.phase, Plugin)  # narrow type

        self.phase.go(
            guest=guest,
            logger=logger)

    def go(self) -> Generator[TaskOutcome['Self'], None, None]:
        # Based on the phase, pick the proper parent class' go()
        if isinstance(self.phase, Action):
            yield from GuestlessTask.go(self)

        else:
            yield from Task.go(self)


class PhaseQueue(Queue[QueuedPhase]):
    """ Queue class for running phases on guests """

    def enqueue(
            self,
            *,
            phase: Union[Action, Plugin],
            guests: List['Guest']) -> None:
        """
        Add a phase to queue.

        Phase will be executed on given guests, starting at the same time.

        :param phase: phase to run.
        :param guests: one or more guests to run the phase on.
        """

        if not guests:
            raise tmt.utils.MetadataError(
                f'No guests queued for phase "{phase}". A typo in "where" key?')

        self.enqueue_task(QueuedPhase(
            phase=phase,
            guests=guests,
            logger=phase._logger
            ))


@dataclasses.dataclass
class PushTask(Task):
    """ Task performing a workdir push to a guest """

    @property
    def name(self) -> str:
        return 'push'

    def run_on_guest(self, guest: 'Guest', logger: tmt.log.Logger) -> None:
        guest.push()


@dataclasses.dataclass
class PullTask(Task):
    """ Task performing a workdir pull from a guest """

    source: Optional[Path] = None

    @property
    def name(self) -> str:
        return 'pull'

    def run_on_guest(self, guest: 'Guest', logger: tmt.log.Logger) -> None:
        guest.pull(source=self.source)


GuestSyncTaskT = TypeVar('GuestSyncTaskT', PushTask, PullTask)


def sync_with_guests(
        step: Step,
        action: str,
        task: GuestSyncTaskT,
        logger: tmt.log.Logger) -> None:
    """
    Push and pull stuff from guests in a parallel manner.

    Used by steps that run their plugins against one or more guest. Based on
    a :py:class:`PhaseQueue` primitive, parallelized push/pull operations are
    needed, and this function handles the details.

    :param step: step managing the sync operation.
    :param action: ``push`` or ``pull`, used for nicer logging.
    :param task: :py:class:`PushTask` or :py:class:`PullTask` which represents
        the actual operation.
    :param logger: logger to use for logging.
    """

    queue: Queue[GuestSyncTaskT] = Queue(
        action,
        logger.descend(logger_name=action))

    queue.enqueue_task(task)

    failed_actions: List[TaskOutcome[GuestSyncTaskT]] = []

    for outcome in queue.run():
        if outcome.exc:
            outcome.logger.fail(str(outcome.exc))

            failed_actions.append(outcome)
            continue

    if failed_actions:
        # TODO: needs a better message...
        # Shall be fixed with https://github.com/teemtee/tmt/pull/2094
        raise tmt.utils.GeneralError(f'{step.__class__.__name__.lower()} step failed') \
            from failed_actions[0].exc
