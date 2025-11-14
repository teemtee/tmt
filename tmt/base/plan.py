#: Filename associated with ``TMT_PLAN_SOURCE_SCRIPT``
PLAN_SOURCE_SCRIPT_NAME: str = "plan-source-script.sh"


class _RemotePlanReference(_RawFmfId):
    importing: Optional[str]
    scope: Optional[str]
    inherit_context: Optional[bool]
    inherit_environment: Optional[bool]
    adjust_plans: list[Any]


class RemotePlanReferenceImporting(enum.Enum):
    REPLACE = 'replace'
    BECOME_PARENT = 'become-parent'

    @classmethod
    def from_spec(cls, spec: str) -> 'RemotePlanReferenceImporting':
        try:
            return RemotePlanReferenceImporting(spec)
        except ValueError as error:
            raise tmt.utils.SpecificationError(
                f"Invalid remote plan replacement '{spec}'."
            ) from error


class RemotePlanReferenceImportScope(enum.Enum):
    FIRST_PLAN_ONLY = 'first-plan-only'
    SINGLE_PLAN_ONLY = 'single-plan-only'
    ALL_PLANS = 'all-plans'

    @classmethod
    def from_spec(cls, spec: str) -> 'RemotePlanReferenceImportScope':
        try:
            return RemotePlanReferenceImportScope(spec)
        except ValueError as error:
            raise tmt.utils.SpecificationError(
                f"Invalid remote plan match scope '{spec}'."
            ) from error


@container
class RemotePlanReference(
    FmfId,
    # Repeat the SpecBasedContainer, with more fitting in/out spec type.
    SpecBasedContainer[_RemotePlanReference, _RemotePlanReference],
):
    VALID_KEYS: ClassVar[list[str]] = [
        *FmfId.VALID_KEYS,
        'importing',
        'scope',
        'inherit-context',
        'inherit-environment',
        'adjust-plans',
    ]

    importing: RemotePlanReferenceImporting = RemotePlanReferenceImporting.REPLACE
    scope: RemotePlanReferenceImportScope = RemotePlanReferenceImportScope.FIRST_PLAN_ONLY
    inherit_context: bool = True
    inherit_environment: bool = True
    # Note: normalize_adjust returns a list as per its type hint
    adjust_plans: list[_RawAdjustRule] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_adjust,
    )

    @functools.cached_property
    def name_pattern(self) -> Pattern[str]:
        assert self.name is not None

        try:
            return re.compile(self.name)

        except Exception as exc:
            raise tmt.utils.SpecificationError(
                "Invalid regular expression used as remote plan name."
            ) from exc

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_dict(self) -> _RemotePlanReference:  # type: ignore[override]
        return cast(_RemotePlanReference, super().to_dict())

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_minimal_dict(self) -> _RemotePlanReference:  # type: ignore[override]
        """
        Convert to a mapping with unset keys omitted
        """

        return cast(_RemotePlanReference, super().to_minimal_dict())

    def to_spec(self) -> _RemotePlanReference:
        """
        Convert to a form suitable for saving in a specification file
        """

        spec = self.to_dict()

        spec['importing'] = self.importing.value
        spec['scope'] = self.scope.value

        return spec

    def to_minimal_spec(self) -> _RemotePlanReference:
        """
        Convert to specification, skip default values
        """

        spec = self.to_minimal_dict()

        spec['importing'] = self.importing.value
        spec['scope'] = self.scope.value

        return spec

    # ignore[override]: expected, we do want to accept and return more
    # specific types than those declared in superclass.
    @classmethod
    def from_spec(cls, raw: _RemotePlanReference) -> 'RemotePlanReference':  # type: ignore[override]
        """
        Convert from a specification file or from a CLI option
        """

        # TODO: with mandatory validation, this can go away.
        ref = raw.get('ref', None)
        if not isinstance(ref, (type(None), str)):
            # TODO: deliver better key address
            raise tmt.utils.NormalizationError('ref', ref, 'unset or a string')

        reference = RemotePlanReference()

        for key in ('url', 'ref', 'name'):
            raw_value = raw.get(key, None)

            setattr(reference, key, None if raw_value is None else str(raw_value))

        for key in ('path',):
            raw_path = cast(Optional[str], raw.get(key, None))
            setattr(reference, key, Path(raw_path) if raw_path is not None else None)

        reference.importing = RemotePlanReferenceImporting.from_spec(
            str(raw.get('importing', RemotePlanReferenceImporting.REPLACE.value))
        )
        reference.scope = RemotePlanReferenceImportScope.from_spec(
            str(raw.get('scope', RemotePlanReferenceImportScope.FIRST_PLAN_ONLY.value))
        )
        reference.inherit_context = bool(raw.get('inherit-context', True))
        reference.inherit_environment = bool(raw.get('inherit-environment', True))
        reference.adjust_plans = cast(list[_RawAdjustRule], raw.get('adjust-plans', []))

        return reference


@container(repr=False)
class Plan(
    HasRunWorkdir,
    HasPlanWorkdir,
    HasEnvironment,
    Core,
    tmt.export.Exportable['Plan'],
    tmt.lint.Lintable['Plan'],
):
    """
    Plan object (L2 Metadata)
    """

    # `environment` and `environment-file` are NOT promoted to instance variables.
    context: FmfContext = field(
        default_factory=FmfContext,
        normalize=tmt.utils.FmfContext.from_spec,
        exporter=lambda value: value.to_spec(),
    )
    gate: list[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list,
    )

    # Optional Login instance attached to the plan for easy login in tmt try
    login: Optional[tmt.steps.Login] = None

    # Optional Ansible configuration for the plan
    ansible: Optional[tmt.ansible.PlanAnsible] = field(
        default=None,
        normalize=tmt.ansible.normalize_plan_ansible,
        exporter=lambda value: value.to_spec() if value else None,
    )

    # When fetching remote plans or splitting plans, we store links
    # between the original plan with the fmf id and the imported or
    # derived plans with the content.
    _original_plan: Optional['Plan'] = field(default=None, internal=True)
    _original_plan_fmf_id: Optional[FmfId] = field(default=None, internal=True)

    _imported_plan_references: list[RemotePlanReference] = field(
        default_factory=list, internal=True
    )
    _imported_plans: list['Plan'] = field(default_factory=list, internal=True)

    _derived_plans: list['Plan'] = field(default_factory=list, internal=True)
    derived_id: Optional[int] = field(default=None, internal=True)

    #: Used by steps to mark invocations that have been already applied to
    #: this plan's phases. Needed to avoid the second evaluation in
    #: py:meth:`Step.wake()`.
    _applied_cli_invocations: list['tmt.cli.CliInvocation'] = field(
        default_factory=list, internal=True
    )

    _extra_l2_keys = [
        'context',
        'environment',
        'environment-file',
        'gate',
        'ansible',
    ]

    def __init__(
        self,
        *,
        node: fmf.Tree,
        tree: Optional['Tree'] = None,
        run: Optional['Run'] = None,
        skip_validation: bool = False,
        raise_on_validation_error: bool = False,
        inherited_fmf_context: Optional[FmfContext] = None,
        inherited_environment: Optional[Environment] = None,
        logger: tmt.log.Logger,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the plan
        """
        kwargs.setdefault('run', run)
        super().__init__(
            node=node,
            tree=tree,
            logger=logger,
            parent=run,
            skip_validation=skip_validation,
            raise_on_validation_error=raise_on_validation_error,
            **kwargs,
        )

        # TODO: there is a bug in handling internal fields with `default_factory`
        # set, incorrect default value is generated, and the field ends up being
        # set to `None`. See https://github.com/teemtee/tmt/issues/2630.
        self._applied_cli_invocations = []
        self._imported_plan_references = []
        self._imported_plans = []
        self._derived_plans = []
        self._fmf_context_from_importing = inherited_fmf_context or FmfContext()
        self._environment_from_importing = inherited_environment or Environment()

        # Check for possible remote plan reference first
        reference = self.node.get(['plan', 'import'])
        if reference is not None:
            self._imported_plan_references = [RemotePlanReference.from_spec(reference)]

        # Save the run, prepare worktree and plan data directory
        self.my_run = run
        self.worktree: Optional[Path] = None
        if self.my_run:
            # Skip to initialize the work tree if the corresponding option is
            # true. Note that 'tmt clean' consumes the option because it
            # should not initialize the work tree at all.
            if not self.my_run.opt(tmt.utils.PLAN_SKIP_WORKTREE_INIT):
                self._initialize_worktree()

            self._initialize_data_directory()

        # Expand all environment and context variables in the node
        with self.environment.as_environ():
            expand_node_data(node.data, self.fmf_context)

        # Initialize test steps
        self.discover = tmt.steps.discover.Discover(
            logger=logger.descend(logger_name='discover'),
            plan=self,
            data=self.node.get('discover'),
        )
        self.provision = tmt.steps.provision.Provision(
            logger=logger.descend(logger_name='provision'),
            plan=self,
            data=self.node.get('provision'),
        )
        self.prepare = tmt.steps.prepare.Prepare(
            logger=logger.descend(logger_name='prepare'),
            plan=self,
            data=self.node.get('prepare'),
        )
        self.execute = tmt.steps.execute.Execute(
            logger=logger.descend(logger_name='execute'),
            plan=self,
            data=self.node.get('execute'),
        )
        self.report = tmt.steps.report.Report(
            logger=logger.descend(logger_name='report'),
            plan=self,
            data=self.node.get('report'),
        )
        self.finish = tmt.steps.finish.Finish(
            logger=logger.descend(logger_name='finish'),
            plan=self,
            data=self.node.get('finish'),
        )
        self.cleanup = tmt.steps.cleanup.Cleanup(
            logger=logger.descend(logger_name='cleanup'),
            plan=self,
            data=self.node.get('cleanup'),
        )

        self._update_metadata()

    @property
    def plan_workdir(self) -> Path:
        if self.workdir is None:
            raise GeneralError(
                f"Existence of a plan '{self.name}' workdir"
                " was presumed but the workdir does not exist."
            )

        return self.workdir

    @property
    def run_workdir(self) -> Path:
        if self.my_run is None:
            raise GeneralError('Existence of a run was presumed but the run does not exist.')

        return self.my_run.run_workdir

    # TODO: better, more elaborate ways of assigning serial numbers to tests
    # can be devised - starting with a really trivial one: each test gets
    # one, starting with `1`.
    #
    # For now, the test itself is not important, and it's part of the method
    # signature to leave the door open for more sophisticated methods that
    # might depend on the actual test properties. Our simple "increment by 1"
    # method does not need it.
    _test_serial_number_generator: Optional[Iterator[int]] = None

    def draw_test_serial_number(self, test: Test) -> int:
        if self._test_serial_number_generator is None:
            self._test_serial_number_generator = itertools.count(start=1, step=1)

        return next(self._test_serial_number_generator)

    #
    # Plan environment and its components
    #

    # Q: what part of plan environment or context should be "inheritable"
    #    by imported plans?
    #
    # A: Only what the plan truly and fully owns: its own `environment`
    #    and `environment-file` keys, `context` key, and environment
    #    and context inherited from its importing plan if this one was
    #    also imported.
    #
    #    No "shared" environment shall be part of the "inheritable" bundle.
    #    By leaving CLI inputs or plan environment file out, we make the
    #    inheritance clearer, without duplicities, and the composition
    #    is then easier to extend or debug.

    #: Environment variables inherited from the importing plan. If the
    #: plan was not imported, the set will be empty.
    _environment_from_importing: Environment = field(default_factory=Environment, internal=True)

    @property
    def _environment_from_intrinsics(self) -> Environment:
        """
        Environment variables derived from the plan properties.
        """

        environment = Environment(
            {
                'TMT_VERSION': EnvVarValue(tmt.__version__),
            }
        )

        if self.worktree:
            environment['TMT_TREE'] = EnvVarValue(self.worktree)

        if self.my_run:
            environment['TMT_PLAN_DATA'] = EnvVarValue(self.data_directory)
            environment['TMT_PLAN_ENVIRONMENT_FILE'] = EnvVarValue(self.plan_environment_file)
            environment['TMT_PLAN_SOURCE_SCRIPT'] = EnvVarValue(self.plan_source_script)

        return environment

    @property
    def _environment_from_fmf(self) -> Environment:
        """
        Environment variables from ``environment`` and ``environment-file`` keys.
        """

        return Environment.from_inputs(
            raw_fmf_environment_files=self.node.get("environment-file") or [],
            raw_fmf_environment=self.node.get('environment', {}),
            file_root=Path(self.node.root) if self.node.root else None,
            key_address=self.node.name,
            logger=self._logger,
        )

    @property
    def _environment_from_cli(self) -> Environment:
        """
        Environment variables from ``--environment`` and ``--environment-file`` options.
        """

        return Environment.from_inputs(
            raw_cli_environment_files=self.opt('environment-file') or [],
            raw_cli_environment=self.opt('environment'),
            file_root=Path(self.node.root) if self.node.root else None,
            key_address=self.node.name,
            logger=self._logger,
        )

    @property
    def _environment_from_plan_environment_file(self) -> Environment:
        """
        Environment sourced from the :ref:`plan environment file <step-variables>`.
        """

        if (
            self.my_run
            and self.plan_environment_file.exists()
            and self.plan_environment_file.stat().st_size > 0
        ):
            return tmt.utils.Environment.from_file(
                filename=self.plan_environment_file.name,
                root=self.plan_environment_file.parent,
                logger=self._logger,
            )

        return Environment()

    @property
    def environment(self) -> Environment:
        """
        Environment variables of the plan.

        Contains all environment variables collected from multiple
        sources (in the following order):

        * :ref:`plan environment file <step-variables>`,
        * plan's ``environment`` and ``environment-file`` keys,
        * importing plan's environment,
        * ``--environment`` and ``--environment-file`` options,
        * run's environment,
        * plan's properties.
        """

        if self.my_run:
            return Environment(
                {
                    **self._environment_from_plan_environment_file,
                    **self._environment_from_fmf,
                    **self._environment_from_importing,
                    **self._environment_from_cli,
                    **self.my_run.environment,
                    **self._environment_from_intrinsics,
                }
            )

        return Environment(
            {
                **self._environment_from_fmf,
                **self._environment_from_importing,
                **self._environment_from_cli,
                **self._environment_from_intrinsics,
            }
        )

    @property
    def _inheritable_environment(self) -> Environment:
        """
        A subset of plan environment variables imported plans can inherit.

        Contains environment variables collected from the following
        sources (in the order):

        * plan's ``environment`` and ``environment-file`` keys,
        * importing plan's environment.
        """

        return Environment(
            {
                **self._environment_from_fmf,
                **self._environment_from_importing,
            }
        )

    #
    # Plan fmf context and its components
    #

    #: Fmf context inherited from the importing plan. If the plan was
    #: not imported, the set will be empty.
    _fmf_context_from_importing: FmfContext = field(default_factory=FmfContext, internal=True)

    @property
    def fmf_context(self) -> tmt.utils.FmfContext:
        """
        Fmf context of the plan.

        Contains all context dimensions collected from multiple sources
        (in the following order):

        * plan's ``context`` key,
        * importing plan's context,
        * ``--context`` option.
        """

        return FmfContext(
            {**self.context, **self._fmf_context_from_importing, **self._fmf_context_from_cli}
        )

    @property
    def _inheritable_fmf_context(self) -> FmfContext:
        """
        A subset of plan fmf context imported plans can inherit.

        Contains context dimensions collected from the following sources
        (in the order):

        * plan's ``context`` key,
        * importing plan's context.
        """

        return FmfContext(
            {
                **self.context,
                **self._fmf_context_from_importing,
            }
        )

    @property
    def _noninheritable_fmf_context(self) -> FmfContext:
        """
        A subset of plan fmf context imported plans cannot inherit.

        Contains context dimensions collected from the following sources
        (in the order):

        * ``--context`` option.
        """

        return self._fmf_context_from_cli

    def _initialize_worktree(self) -> None:
        """
        Prepare the worktree, a copy of the metadata tree root

        Used as cwd in prepare, execute and finish steps.
        """

        # Do nothing for remote plan reference
        if self.is_remote_plan_reference:
            return

        # Prepare worktree path and detect the source tree root
        self.worktree = self.plan_workdir / 'tree'
        tree_root = Path(self.node.root) if self.node.root else None

        # Create an empty directory if there's no metadata tree
        if not tree_root:
            self.debug('Create an empty worktree (no metadata tree).', level=2)
            self.worktree.mkdir(exist_ok=True)
            return

        # Sync metadata root to the worktree
        self.debug(f"Sync the worktree to '{self.worktree}'.", level=2)

        ignore: list[Path] = [Path('.git')]

        # If we're in a git repository, honor .gitignore; xref
        # https://stackoverflow.com/questions/13713101/rsync-exclude-according-to-gitignore-hgignore-svnignore-like-filter-c  # noqa: E501
        git_root = tmt.utils.git.git_root(fmf_root=tree_root, logger=self._logger)
        if git_root:
            ignore.extend(tmt.utils.git.git_ignore(root=git_root, logger=self._logger))

        self.debug(
            "Ignoring the following paths during worktree sync",
            tmt.utils.format_value(ignore),
            level=4,
        )

        with tempfile.NamedTemporaryFile(mode='w') as excludes_tempfile:
            excludes_tempfile.write('\n'.join(str(path) for path in ignore))

            # Make sure ignored paths are saved before telling rsync to use them.
            # With Python 3.12, we could use `delete_on_false=False` and call `close()`.
            excludes_tempfile.flush()

            # Note: rsync doesn't use reflinks right now, so in the future it'd be even better to
            # use e.g. `cp` but filtering out the above.
            self.run(
                Command(
                    "rsync",
                    "-ar",
                    "--exclude-from",
                    excludes_tempfile.name,
                    f"{tree_root}/",
                    self.worktree,
                )
            )

    def _initialize_data_directory(self) -> None:
        """
        Create the plan data directory

        This is used for storing logs and other artifacts created during
        prepare step, test execution or finish step and which are pulled
        from the guest for possible future inspection.
        """
        self.data_directory = self.plan_workdir / "data"
        self.debug(f"Create the data directory '{self.data_directory}'.", level=2)
        self.data_directory.mkdir(exist_ok=True, parents=True)

    @functools.cached_property
    def plan_environment_file(self) -> Path:
        assert self.data_directory is not None  # narrow type

        plan_environment_file_path = self.data_directory / "variables.env"
        plan_environment_file_path.touch(exist_ok=True)

        self.debug(f"Create the environment file '{plan_environment_file_path}'.", level=2)

        return plan_environment_file_path

    @functools.cached_property
    def plan_source_script(self) -> Path:
        assert self.data_directory is not None  # narrow type

        plan_sourced_file_path = self.data_directory / PLAN_SOURCE_SCRIPT_NAME
        plan_sourced_file_path.touch(exist_ok=True)

        self.debug(f"Create the environment file '{plan_sourced_file_path}'.", level=2)

        return plan_sourced_file_path

    @staticmethod
    def edit_template(raw_content: str) -> str:
        """
        Edit the default template with custom values
        """

        content = tmt.utils.yaml_to_dict(raw_content)

        # For each step check for possible command line data
        for step in tmt.steps.STEPS:
            options = Plan._opt(step)
            if not options:
                continue
            # TODO: it'd be nice to annotate things here and there, template
            # is not a critical, let's go with Any for now
            step_data: Any = []

            # For each option check for valid yaml and store
            for option in options:
                try:
                    # FIXME: Ruamel.yaml "remembers" the used formatting when
                    #        using round-trip mode and since it comes from the
                    #        command-line, no formatting is applied resulting
                    #        in inconsistent formatting. Using a safe loader in
                    #        this case is a hack to make it forget, though
                    #        there may be a better way to do this.
                    try:
                        data: dict[str, Any] = tmt.utils.yaml_to_dict(option, yaml_type='safe')
                        if not (data):
                            raise tmt.utils.GeneralError("Step data cannot be empty.")
                    except tmt.utils.GeneralError as error:
                        raise tmt.utils.GeneralError(
                            f"Invalid step data for {step}: '{option}'."
                        ) from error
                    step_data.append(data)
                except MarkedYAMLError as error:
                    raise tmt.utils.GeneralError(f"Invalid yaml data for {step}.") from error

            # Use list only when multiple step data provided
            if len(step_data) == 1:
                step_data = step_data[0]
            content[step] = step_data

        return to_yaml(content)

    @staticmethod
    def overview(tree: 'Tree') -> None:
        """
        Show overview of available plans
        """
        plans = [style(str(plan), fg='red') for plan in tree.plans()]
        echo(
            style(
                'Found {}{}{}.'.format(
                    listed(plans, 'plan'), ': ' if plans else '', listed(plans, max=12)
                ),
                fg='blue',
            )
        )

    @staticmethod
    def create(
        *,
        names: list[str],
        template: str,
        path: Path,
        force: bool = False,
        dry: Optional[bool] = None,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Create a new plan
        """
        # Prepare paths
        if dry is None:
            dry = Plan._opt('dry')

        # Get plan template
        if tmt.utils.is_url(template):
            plan_content = tmt.templates.MANAGER.render_from_url(template, logger)
        else:
            plan_templates = tmt.templates.MANAGER.templates['plan']
            try:
                plan_content = tmt.templates.MANAGER.render_file(plan_templates[template])
            except KeyError as error:
                raise tmt.utils.GeneralError(f"Invalid template '{template}'.") from error

        # Override template with data provided on command line
        plan_content = Plan.edit_template(plan_content)

        # Append link with appropriate relation
        links = Links(data=list(cast(list[_RawLink], Plan._opt('link', []))))
        if links:  # Output 'links' if and only if it is not empty
            plan_content += to_yaml({'link': links.to_spec()})

        for plan_name in names:
            plan_path = path / Path(plan_name).unrooted()

            if plan_path.suffix != '.fmf':
                plan_path = plan_path.parent / f'{plan_path.name}.fmf'

            # Create directory & plan
            tmt.utils.create_directory(
                path=plan_path.parent,
                name='plan directory',
                dry=dry,
                logger=logger,
            )

            tmt.utils.create_file(
                path=plan_path,
                name='plan',
                content=plan_content,
                dry=dry,
                force=force,
                logger=logger,
            )

            if links.get('verifies') and dry is False:
                plans = Tree(path=path, logger=logger).plans(
                    names=[f"^{plan_name}$"], apply_command_line=False
                )
                tmt.utils.jira.link(tmt_objects=plans, links=links, logger=logger)

    def _iter_steps(
        self, enabled_only: bool = True, skip: Optional[list[str]] = None
    ) -> Iterator[tuple[tmt.steps.StepName, tmt.steps.Step]]:
        """
        Iterate over steps.

        :param enabled_only: if set, only enabled steps would be listed.
        :param skip: if step name is in this list, it would be skipped.
        :yields: tuple of two items, step name and corresponding instance of
            :py:class:`tmt.step.Step`.
        """
        skip = skip or []
        for name in tmt.steps.STEPS:
            if name in skip:
                continue
            step = cast(tmt.steps.Step, getattr(self, name))
            if step.enabled or enabled_only is False:
                yield (name, step)

    def steps(
        self, enabled_only: bool = True, skip: Optional[list[str]] = None
    ) -> Iterator[tmt.steps.Step]:
        """
        Iterate over steps.

        :param enabled_only: if set, only enabled steps would be listed.
        :param skip: if step name is in this list, it would be skipped.
        :yields: instance of :py:class:`tmt.step.Step`, representing each step.
        """
        for _, step in self._iter_steps(enabled_only=enabled_only, skip=skip):
            yield step

    def step_names(
        self, enabled_only: bool = True, skip: Optional[list[str]] = None
    ) -> Iterator[tmt.steps.StepName]:
        """
        Iterate over step names.

        :param enabled_only: if set, only enabled steps would be listed.
        :param skip: if step name is in this list, it would be skipped.
        :yields: step names.
        """
        for name, _ in self._iter_steps(enabled_only=enabled_only, skip=skip):
            yield name

    def show(self) -> None:
        """
        Show plan details
        """

        # Summary, description and contact first
        self.ls(summary=True)
        if self.description:
            echo(tmt.utils.format('description', self.description, key_color='green'))
        if self.author:
            echo(tmt.utils.format('author', self.author, key_color='green'))
        if self.contact:
            echo(tmt.utils.format('contact', self.contact, key_color='green'))

        # Individual step details
        for step in self.steps(enabled_only=False):
            step.show()

        # Environment and context
        if self.environment:
            echo(tmt.utils.format('environment', self.environment, key_color='blue'))
        if self.fmf_context:
            echo(
                tmt.utils.format(
                    'context',
                    self.fmf_context,
                    key_color='blue',
                    list_format=tmt.utils.ListFormat.SHORT,
                )
            )

        # The rest
        echo(tmt.utils.format('enabled', self.enabled, key_color='cyan'))
        if self.order != DEFAULT_ORDER:
            echo(tmt.utils.format('order', self.order, key_color='cyan'))
        if self.id:
            echo(tmt.utils.format('id', self.id, key_color='cyan'))
        if self.tag:
            echo(tmt.utils.format('tag', self.tag, key_color='cyan'))
        if self.tier:
            echo(tmt.utils.format('tier', self.tier, key_color='cyan'))
        if self.link is not None:
            self.link.show()
        if self.verbosity_level:
            self._show_additional_keys()

        # Show fmf id of the remote plan in verbose mode
        if (self._original_plan or self._imported_plan_references) and self.verbosity_level:
            # Pick fmf id from the original plan by default, use the
            # current plan in shallow mode when no plans are fetched.

            def _show_imported(reference: RemotePlanReference) -> None:
                echo(tmt.utils.format('import', '', key_color='blue'))

                for key, value in reference.items():
                    echo(tmt.utils.format(key, value, key_color='green'))

            if self._original_plan is not None:
                for reference in self._original_plan._imported_plan_references:
                    _show_imported(reference)

            else:
                for reference in self._imported_plan_references:
                    _show_imported(reference)

    # FIXME - Make additional attributes configurable
    def lint_unknown_keys(self) -> LinterReturn:
        """
        P001: all keys are known
        """

        invalid_keys = self._lint_keys(
            list(self.step_names(enabled_only=False)) + self._extra_l2_keys
        )

        if invalid_keys:
            for key in invalid_keys:
                yield LinterOutcome.FAIL, f'unknown key "{key}" is used'

            return

        yield LinterOutcome.PASS, 'correct keys are used'

    def lint_execute_not_defined(self) -> LinterReturn:
        """
        P002: execute step must be defined with "how"
        """

        if not self.node.get('execute'):
            yield LinterOutcome.FAIL, 'execute step must be defined with "how"'
            return

        yield LinterOutcome.PASS, 'execute step defined with "how"'

    def _step_phase_nodes(self, step: str) -> list[dict[str, Any]]:
        """
        List raw fmf nodes for the given step
        """

        _phases = self.node.get(step)

        if not _phases:
            return []

        if isinstance(_phases, dict):
            return [_phases]

        return cast(list[dict[str, Any]], _phases)

    def _lint_step_methods(self, step: str, plugin_class: tmt.steps.PluginClass) -> LinterReturn:
        """
        P003: execute step methods must be known
        """

        phases = self._step_phase_nodes(step)

        if not phases:
            yield LinterOutcome.SKIP, f'{step} step is not defined'
            return

        methods = [method.name for method in plugin_class.methods()]

        invalid_phases = [phase for phase in phases if phase.get('how') not in methods]

        if invalid_phases:
            for phase in invalid_phases:
                yield (
                    LinterOutcome.FAIL,
                    f'unknown {step} method "{phase.get("how")}" in "{phase.get("name")}"',
                )

            return

        yield LinterOutcome.PASS, f'{step} step methods are all known'

    # TODO: can we use self.discover & its data instead? A question to be answered
    # by better schema & lint cooperation - e.g. unknown methods shall be reported
    # by schema-based validation already.
    def lint_execute_unknown_method(self) -> LinterReturn:
        """
        P003: execute step methods must be known
        """

        yield from self._lint_step_methods(
            'execute',
            tmt.steps.execute.ExecutePlugin,  # type: ignore[type-abstract]
        )

    def lint_discover_unknown_method(self) -> LinterReturn:
        """
        P004: discover step methods must be known
        """

        yield from self._lint_step_methods(
            'discover',
            tmt.steps.discover.DiscoverPlugin,  # type: ignore[type-abstract]
        )

    def lint_fmf_remote_ids_valid(self) -> LinterReturn:
        """
        P005: remote fmf ids must be valid
        """

        fmf_ids: list[tuple[FmfId, dict[str, Any]]] = []

        for phase in self._step_phase_nodes('discover'):
            if phase.get('how') != 'fmf':
                continue

            # Skipping `name` on purpose - that belongs to the whole step,
            # it's not treated as part of fmf id.
            fmf_id_data = cast(
                _RawFmfId,
                {key: value for key, value in phase.items() if key in ['url', 'ref', 'path']},
            )

            if not fmf_id_data:
                continue

            fmf_ids.append((FmfId.from_spec(fmf_id_data), phase))

        if fmf_ids:
            for fmf_id, phase in fmf_ids:
                valid, error = fmf_id.validate()

                if valid:
                    yield LinterOutcome.PASS, f'remote fmf id in "{phase.get("name")}" is valid'

                else:
                    yield (
                        LinterOutcome.FAIL,
                        f'remote fmf id in "{phase.get("name")}" is invalid, {error}',
                    )

            return

        yield LinterOutcome.SKIP, 'no remote fmf ids defined'

    def lint_unique_names(self) -> LinterReturn:
        """
        P006: phases must have unique names
        """
        passed = True
        for step_name in self.step_names(enabled_only=False):
            phase_name: str
            for phase_name in tmt.utils.duplicates(
                phase.get('name', None) for phase in self._step_phase_nodes(step_name)
            ):
                passed = False
                yield (
                    LinterOutcome.FAIL,
                    f"duplicate phase name '{phase_name}' in step '{step_name}'",
                )
        if passed:
            yield LinterOutcome.PASS, 'phases have unique names'

    def lint_phases_have_guests(self) -> LinterReturn:
        """
        P007: step phases require existing guests and roles
        """

        guest_names: list[str] = []
        guest_roles: list[str] = []

        for i, phase in enumerate(self._step_phase_nodes('provision')):
            guest_name = cast(Optional[str], phase.get('name'))

            if not guest_name:
                guest_name = f'{tmt.utils.DEFAULT_NAME}-{i}'

            guest_names.append(guest_name)

            if phase.get('role'):
                guest_roles.append(phase['role'])

        names_formatted = ', '.join(f"'{name}'" for name in sorted(tmt.utils.uniq(guest_names)))
        roles_formatted = ', '.join(f"'{role}'" for role in sorted(tmt.utils.uniq(guest_roles)))

        def _lint_step(step: str) -> LinterReturn:
            for phase in self._step_phase_nodes(step):
                wheres = tmt.utils.normalize_string_list(
                    f'{self.name}:{step}', phase.get('where'), self._logger
                )

                if not wheres:
                    yield (
                        LinterOutcome.PASS,
                        f"{step} phase '{phase.get('name')}' does not require specific guest",
                    )
                    continue

                for where in wheres:
                    if where in guest_names:
                        yield (
                            LinterOutcome.PASS,
                            f"{step} phase '{phase.get('name')}' shall run on guest '{where}'",
                        )
                        continue

                    if where in guest_roles:
                        yield (
                            LinterOutcome.PASS,
                            f"{step} phase '{phase.get('name')}' shall run on role '{where}'",
                        )
                        continue

                    if guest_names and guest_roles:
                        yield (
                            LinterOutcome.FAIL,
                            f"{step} phase '{phase.get('name')}' needs guest or role '{where}',"
                            f" guests {names_formatted} and roles {roles_formatted} were found",
                        )

                    elif guest_names:
                        yield (
                            LinterOutcome.FAIL,
                            f"{step} phase '{phase.get('name')}' needs guest or role "
                            f"'{where}', guests {names_formatted} and no roles were found",
                        )

                    else:
                        yield (
                            LinterOutcome.FAIL,
                            f"{step} phase '{phase.get('name')}' needs guest or role "
                            f"'{where}', roles {roles_formatted} and no guests were found",
                        )

        yield from _lint_step('prepare')
        yield from _lint_step('execute')
        yield from _lint_step('finish')

    def lint_empty_env_files(self) -> LinterReturn:
        """
        P008: environment files are not empty
        """

        env_files = self.node.get("environment-file") or []

        if not env_files:
            yield LinterOutcome.SKIP, 'no environment files found'
            return

        for env_file in env_files:
            env_file = (self.anchor_path / Path(env_file)).resolve()
            if not env_file.stat().st_size:
                yield LinterOutcome.FAIL, f"the environment file '{env_file}' is empty"
                return

        yield LinterOutcome.PASS, 'no empty environment files'

    def lint_step_data_is_valid(self) -> LinterReturn:
        """
        P009: step phases have valid data
        """
        passed = True
        for step in self.steps(enabled_only=False):
            # Replicate the initialization inside step._normalize_data
            for raw_data in step._raw_data:
                try:
                    step._plugin_base_class.delegate(step, raw_data=raw_data)
                except Exception:
                    passed = False
                    fail_msg = f"{step} step has invalid data for phase '{raw_data['name']}'"
                    yield LinterOutcome.FAIL, fail_msg
        if passed:
            yield LinterOutcome.PASS, "All step data is valid"

    def wake(self) -> None:
        """
        Wake up all steps
        """

        self.debug('wake', color='cyan', shift=0, level=2)
        for step in self.steps(enabled_only=False):
            self.debug(str(step), color='blue', level=2)
            try:
                step.wake()
            except tmt.utils.SpecificationError as error:
                # Re-raise the exception if the step is enabled (invalid
                # step data), otherwise just warn the user and continue.
                if step.enabled:
                    raise error

                step.warn(str(error))

    def header(self) -> None:
        """
        Show plan name and summary

        Include one blank line to separate plans
        """
        self.info('')
        self.info(self.name, color='red')
        if self.summary:
            self.verbose('summary', self.summary, 'green')

    def go(self) -> None:
        """
        Execute the plan
        """
        self.header()

        # Additional debug info like plan environment
        self.debug('info', color='cyan', shift=0, level=3)
        # TODO: something better than str()?
        self.debug('environment', self.environment, 'magenta', level=3)
        self.debug('context', self.fmf_context, 'magenta', level=3)

        # Wake up all steps
        self.wake()

        # Set up login and reboot plugins for all steps
        self.debug("action", color="blue", level=2)
        for step in self.steps(enabled_only=False):
            step.setup_actions()

        # Check if steps are not in stand-alone mode
        standalone = set()
        for step in self.steps():
            standalone_plugins = step.plugins_in_standalone_mode
            if standalone_plugins == 1:
                standalone.add(step.name)
            elif standalone_plugins > 1:
                raise tmt.utils.GeneralError(
                    f"Step '{step.name}' has multiple plugin configs which "
                    f"require running on their own. Combination of such "
                    f"configs is not possible."
                )
        if len(standalone) > 1:
            raise tmt.utils.GeneralError(
                f'These steps require running on their own, their combination '
                f'with the given options is not compatible: '
                f'{fmf.utils.listed(standalone)}.'
            )
        if standalone:
            assert self._cli_context_object is not None  # narrow type
            self._cli_context_object.steps = standalone
            self.debug(f"Running the '{next(iter(standalone))}' step as standalone.")

        # Run enabled steps except 'cleanup'
        self.debug('go', color='cyan', shift=0, level=2)
        abort = False
        try:
            for step in self.steps(skip=['cleanup']):
                step.go()

                if isinstance(step, tmt.steps.discover.Discover):
                    tests = step.tests()

                    # Finish plan if no tests found (except dry mode)
                    if not tests and not self.is_dry_run and not step.extract_tests_later:
                        step.info(
                            'warning', 'No tests found, finishing plan.', color='yellow', shift=1
                        )
                        abort = True
                        return

                    if self.my_run and self.reshape(tests):
                        return

                    if not self.is_dry_run:
                        self.execute._results = self.execute.create_results(
                            self.discover.tests(enabled=True)
                        )
                        self.execute.save()

        # Make sure we run 'report' and 'cleanup' steps always if enabled
        finally:
            for step in self.steps(skip=['cleanup', 'report']):
                step.suspend()

            if not abort:
                try:
                    if self.report.enabled and self.report.status() != "done":
                        self.report.go()
                finally:
                    if self.cleanup.enabled:
                        self.cleanup.go()

    def _export(
        self, *, keys: Optional[list[str]] = None, include_internal: bool = False
    ) -> tmt.export._RawExportedInstance:
        data = super()._export(keys=keys, include_internal=include_internal)

        # TODO: `key` is pretty much `option` here, no need for `key_to_option()` call, but we
        # really need to either rename `_extra_l2_keys`, or make sure it does contain keys and
        # not options. Which it does, now.
        for key in self._extra_l2_keys:
            value = self.node.data.get(key)
            if value:
                data[key] = value

        # Export user-defined extra- keys from the node data
        for key in self.node.data:
            if key.startswith(EXTRA_KEYS_PREFIX):
                value = self.node.data.get(key)
                if value:
                    data[key] = value

        data['context'] = self.fmf_context.to_spec()

        for step_name in tmt.steps.STEPS:
            step = cast(tmt.steps.Step, getattr(self, step_name))

            value = step._export(include_internal=include_internal)
            if value:
                data[step.step_name] = value

        return data

    @property
    def is_remote_plan_reference(self) -> bool:
        """
        Check whether the plan is a remote plan reference
        """
        return bool(self._imported_plan_references)

    def _resolve_import_to_nodes(
        self, reference: RemotePlanReference, tree: fmf.Tree
    ) -> Iterator[fmf.Tree]:
        """
        Discover all plan-like fmf nodes in a given tree.
        """

        self.debug(
            f"Looking for plans in '{tree.root}' matching '{reference.name_pattern}'", level=3
        )

        for node in tree.prune(keys=['execute']):
            if reference.name_pattern.match(node.name) is not None:
                yield node

    def _resolve_import_from_git(self, reference: RemotePlanReference) -> Iterator[fmf.Tree]:
        """
        Discover plan-like nodes matching the given reference in its git repo.

        The referenced git repository is cloned, and we will look for
        plan-like fmf nodes in it.
        """

        # TODO: consider better type than inheriting from fully optional fmf id...
        assert reference.url is not None
        assert reference.name is not None

        destination = self.run_workdir / "import" / self.safe_name.lstrip("/")

        if destination.exists():
            self.debug(f"Seems that '{destination}' has been already cloned.", level=3)

        else:
            tmt.utils.git.git_clone(
                url=reference.url, destination=destination, logger=self._logger
            )

        if reference.ref:
            reference.resolve_dynamic_ref(destination, self)

            if reference.ref:
                self.run(Command('git', 'checkout', reference.ref), cwd=destination)

        if reference.path:
            destination = destination / reference.path.unrooted()

        yield from self._resolve_import_to_nodes(reference, fmf.Tree(str(destination)))

    def _resolve_import_from_fmf_cache(self, reference: RemotePlanReference) -> Iterator[fmf.Tree]:
        """
        Discover plan-like nodes matching the given reference in fmf cache.
        """

        # TODO: similar situation as in _resolve_import_from_git
        assert reference.url is not None

        if str(reference.ref).startswith('@'):
            self.debug(
                f"Not enough data to evaluate dynamic ref '{reference.ref}', "
                "going to clone the repository to read dynamic ref definition."
            )

            with tempfile.TemporaryDirectory() as _tmpdirname:
                tmpdirname = Path(_tmpdirname)

                tmt.utils.git.git_clone(
                    url=str(reference.url),
                    destination=tmpdirname,
                    shallow=True,
                    env=None,
                    logger=self._logger,
                )

                self.run(
                    Command('git', 'checkout', 'HEAD', str(reference.ref)[1:]),
                    cwd=tmpdirname,
                )

                reference.resolve_dynamic_ref(tmpdirname, self)

        yield from self._resolve_import_to_nodes(
            reference,
            fmf.utils.fetch_tree(
                tmt.utils.git.clonable_git_url(reference.url),
                reference.ref,
                str(reference.path.unrooted()) if reference.path else '.',
            ),
        )

    def _resolve_import_reference(self, reference: RemotePlanReference) -> list['Plan']:
        """
        Discover and import plans matching a given remote plan reference.

        :param reference: identifies one or more plans to import.
        :returns: list of imported plans.
        """

        if reference.url is None:
            raise tmt.utils.SpecificationError(f"No URL provided for remote plan '{self.name}'.")

        if reference.name is None:
            raise tmt.utils.SpecificationError(f"No name provided for remote plan '{self.name}'.")

        self.debug(
            f"Plan '{self.name}' importing plans '{reference.name}' from '{reference.url}'.",
            level=3,
        )

        def _convert_node(node: fmf.Tree) -> 'Plan':
            """
            Convert a single fmf node to a plan.
            """

            self.debug(f"Turning node '{node.name}' into a plan.", level=3)

            # Prepare fmf context and environment the imported node would inherit.
            inherited_fmf_context = (
                self._inheritable_fmf_context if reference.inherit_context else None
            )
            inherited_environment = (
                self._inheritable_environment if reference.inherit_environment else None
            )

            # Construct ephemeral fmf context and environment we use to
            # adjust and expand the imported node.
            imported_fmf_context = FmfContext.from_spec(
                node.name, node.data.get('context', {}), self._logger
            )

            # For final context inheritance, respect inherit_context setting
            if reference.inherit_context:
                alteration_fmf_context = FmfContext(
                    {
                        **imported_fmf_context,
                        **self._inheritable_fmf_context,
                        **self._noninheritable_fmf_context,
                    }
                )
            else:
                alteration_fmf_context = FmfContext(
                    {**imported_fmf_context, **self._noninheritable_fmf_context}
                )

            # Adjust the imported tree, to let any `adjust` rules defined in it take
            # action, including the adjust-plans rules.
            node.adjust(
                fmf.context.Context(**alteration_fmf_context),
                case_sensitive=False,
                additional_rules=reference.adjust_plans,
            )

            # If the local plan is disabled, disable the imported plan as well
            if not self.enabled:
                node.data['enabled'] = False

            # Put the plan into its position by giving it the correct name
            if reference.importing == RemotePlanReferenceImporting.REPLACE:
                node.name = self.name

            else:
                node.name = f'{self.name}{node.name}'

            return Plan(
                node=node,
                run=self.my_run,
                inherited_fmf_context=inherited_fmf_context,
                inherited_environment=inherited_environment,
                logger=self._logger.clone(),
            )

        def _generate_plans(nodes: Iterable[fmf.Tree]) -> list[Plan]:
            """
            Convert a list of fmf nodes into a list of plans.
            """

            # Collect all imported plans here. Save also the original
            # node, because if we replace the current plan, we lose
            # original names that are better for logging.
            imported_plans: list[tuple[fmf.Tree, Plan]] = []

            for node in nodes:
                if imported_plans:
                    if reference.scope == RemotePlanReferenceImportScope.FIRST_PLAN_ONLY:
                        self.warn(
                            f"Cannot import remote plan '{node.name}' through '{self.name}', "
                            f"already imported '{imported_plans[0][0].name}' as the first plan."
                        )

                        continue

                    if reference.scope == RemotePlanReferenceImportScope.SINGLE_PLAN_ONLY:
                        raise GeneralError(
                            f"Cannot import multiple plans through '{self.name}', "
                            "may import only single plan, and already imported "
                            f"'{imported_plans[0][0].name}'."
                        )

                    if reference.scope == RemotePlanReferenceImportScope.ALL_PLANS:
                        if reference.importing == RemotePlanReferenceImporting.REPLACE:
                            raise GeneralError(
                                f"Cannot import multiple plans through '{self.name}', "
                                f"already replacing '{self.name}' with imported "
                                f"'{imported_plans[0][0].name}'."
                            )

                        if reference.importing == RemotePlanReferenceImporting.BECOME_PARENT:
                            imported_plans.append((node, _convert_node(node.copy())))

                            continue

                    raise GeneralError("Unhandled importing plan state.")

                imported_plans.append((node, _convert_node(node.copy())))

            return [plan for _, plan in imported_plans]

        try:
            # Clone the whole git repository if executing tests (run is attached)
            if self.my_run and not self.my_run.is_dry_run:
                nodes = self._resolve_import_from_git(reference)

            # Use fmf cache for exploring plans (the whole git repo is not needed)
            else:
                nodes = self._resolve_import_from_fmf_cache(reference)

            return _generate_plans(nodes)

        except Exception as exc:
            raise GeneralError(f"Failed to import remote plan from '{self.name}'.") from exc

    def resolve_imports(self) -> list['Plan']:
        """
        Resolve possible references to remote plans.

        :returns: one or more plans **replacing** the current one. The
            current plan may also be one of the returned ones.
        """

        if not self.is_remote_plan_reference:
            return [self]

        if not self._imported_plans:
            for reference in self._imported_plan_references:
                for imported_plan in self._resolve_import_reference(reference):
                    imported_plan._original_plan = self
                    imported_plan._original_plan_fmf_id = self.fmf_id

                    self._imported_plans.append(imported_plan)

        if self.my_run:
            for policy in self.my_run.policies:
                policy.apply_to_plans(plans=self._imported_plans, logger=self._logger)

        return self._imported_plans

    def derive_plan(self, derived_id: int, tests: dict[str, list[Test]]) -> 'Plan':
        """
        Create a new plan derived from this one.

        New plan will inherit its attributes from this plan, its name
        would be combination of this plan's name and ``derived_id``.
        New plan will have its own workdir, a copy of this plan's
        workdir.

        :param derived_id: arbitrary number marking the new plan as Nth
            plan derived from this plan.
        :param tests: lists of tests to limit the new plan to.
        """

        derived_plan = Plan(
            node=self.node, run=self.my_run, logger=self._logger, name=f'{self.name}.{derived_id}'
        )

        derived_plan._original_plan = self
        derived_plan._original_plan_fmf_id = self.fmf_id
        self._derived_plans.append(derived_plan)

        derived_plan.discover._tests = tests
        derived_plan.discover.status('done')

        shutil.copytree(
            self.discover.step_workdir, derived_plan.discover.step_workdir, dirs_exist_ok=True
        )

        # Load results from discovered tests and save them to the execute step.
        derived_plan.execute._results = derived_plan.execute.create_results(
            derived_plan.discover.tests(enabled=True)
        )
        derived_plan.execute.save()

        for step_name in tmt.steps.STEPS:
            getattr(derived_plan, step_name).save()

        return derived_plan

    def prune(self) -> None:
        """
        Remove all uninteresting files from the plan workdir
        """

        logger = self._logger.descend(extra_shift=1)

        logger.verbose(
            f"Prune '{self.name}' plan workdir '{self.plan_workdir}'.", color="magenta", level=3
        )

        if self.worktree:
            logger.debug(f"Prune '{self.name}' worktree '{self.worktree}'.", level=3)
            shutil.rmtree(self.worktree)

        for step in self.steps(enabled_only=False):
            step.prune(logger=step._logger)

    def reshape(self, tests: list['tmt.steps.discover.TestOrigin']) -> bool:
        """
        Change the content of this plan by application of plan shaping plugins.

        :py:mod:`tmt.plugins.plan_shaper` plugins are invoked and may
        mangle this plan and its content. This plan may be even removed
        from the queue, and replaced with many new plans.

        :param tests: tests that should be considered by shaping plugins
            as part of this plan.
        :returns: ``True`` if the plan has been modified, ``False``
            otherwise.
        """

        for shaper_id in tmt.plugins.plan_shapers._PLAN_SHAPER_PLUGIN_REGISTRY.iter_plugin_ids():
            shaper = tmt.plugins.plan_shapers._PLAN_SHAPER_PLUGIN_REGISTRY.get_plugin(shaper_id)

            assert shaper is not None  # narrow type

            if not shaper.check(self, tests):
                self.debug(f"Plan shaper '{shaper_id}' not applicable.")
                continue

            if self.my_run:
                reshaped_plans = list(shaper.apply(self, tests))

                for policy in self.my_run.policies:
                    policy.apply_to_plans(plans=reshaped_plans, logger=self._logger)

                self.my_run.swap_plans(self, *reshaped_plans)

            return True

        return False

    # TODO: Make the str type-hint more narrow
    def add_phase(self, step: Union[str, tmt.steps.Step], phase: tmt.steps.Phase) -> None:
        """
        Add a phase dynamically to the current plan.

        :param step: The (future) step in which to add the phase.
        :param phase: The phase to add to the step.
        """
        if isinstance(step, str):
            if step not in tmt.steps.STEPS:
                raise GeneralError(f"Tried to add to an unknown step: {step}")
            step = getattr(self, step)
        assert isinstance(step, tmt.steps.Step)
        if step.plan != self:
            raise GeneralError(
                f"Tried to add to a step belonging to a different plan: {step.plan}"
            )
        # TODO: Check that the current step/phase is after the current step/phase
        step.add_phase(phase)


Plan.discover_linters()
