import threading
from typing import Any, Optional, cast

import fmf
import fmf.utils

import tmt
import tmt.log
import tmt.steps
import tmt.steps.prepare
import tmt.utils
import tmt.utils.git
from tmt.container import container, field
from tmt.package_managers.bootc import Bootc
from tmt.steps import safe_filename
from tmt.steps.provision import Guest
from tmt.utils import Command, EnvVarValue, ShellScript

PREPARE_WRAPPER_FILENAME = 'tmt-prepare-wrapper.sh'


@container
class PrepareShellData(tmt.steps.prepare.PrepareStepData):
    script: list[ShellScript] = field(
        default_factory=list,
        option=('-s', '--script'),
        multiple=True,
        metavar='SCRIPT',
        help='Shell script to be executed. Can be used multiple times.',
        normalize=tmt.utils.normalize_shell_script_list,
        serialize=lambda scripts: [str(script) for script in scripts],
        unserialize=lambda serialized: [ShellScript(script) for script in serialized],
    )

    url: Optional[str] = field(
        default=None,
        option='--url',
        metavar='REPOSITORY',
        help="""
            URL of a repository to clone. It will be pushed to guests before
            running any scripts,
            and environment variable ``TMT_PREPARE_SHELL_URL_REPOSITORY`` will
            hold its path on the guest.
            """,
    )

    ref: Optional[str] = field(
        default=None,
        option='--ref',
        metavar='REVISION',
        help="""
            Branch, tag or commit to checkout in the git repository
            cloned when ``url`` is specified.
            """,
    )

    # ignore[override] & cast: two base classes define to_spec(), with conflicting
    # formal types.
    def to_spec(self) -> dict[str, Any]:  # type: ignore[override]
        data = cast(dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('shell')
class PrepareShell(tmt.steps.prepare.PreparePlugin[PrepareShellData]):
    """
    Prepare guest using shell (Bash) scripts.

    Default shell options are applied to the script, see the
    :ref:`/spec/tests/test` key specification for more
    details.

    .. code-block:: yaml

        prepare:
            how: shell
            script:
              - sudo dnf install -y 'dnf-command(copr)'
              - sudo dnf copr enable -y psss/tmt
              - sudo dnf install -y tmt

    Scripts can also be fetched from a remote git repository.
    Specify the ``url`` for the repository and optionally ``ref``
    to checkout a specific branch, tag or commit.
    ``TMT_PREPARE_SHELL_URL_REPOSITORY`` will hold the value of the
    repository path.

    .. code-block:: yaml

        prepare:
            how: shell
            url: https://github.com/teemtee/tmt.git
            ref: main
            script: cd $TMT_PREPARE_SHELL_URL_REPOSITORY && make docs

    .. note::

        When testing bootc image mode deployments, tmt will add
        shell scripts as ``RUN`` directives to a containerfile,
        build a new container image, and switch to it. This allows
        the changes to be persistent across reboots.
    """

    _data_class = PrepareShellData
    _url_clone_lock = threading.Lock()
    _cloned_repo_path_envvar_name = 'TMT_PREPARE_SHELL_URL_REPOSITORY'

    def _handle_git_repository(
        self,
        guest: Guest,
        workdir: tmt.utils.Path,
        environment: tmt.utils.Environment,
    ) -> tmt.utils.Path:
        """Handle git repository cloning if URL is specified"""
        assert self.data.url is not None  # Should only be called when URL is set

        repo_path = workdir / "repository"

        if not self.is_dry_run:
            with self._url_clone_lock:
                if not repo_path.exists():
                    repo_path.parent.mkdir(parents=True, exist_ok=True)
                    tmt.utils.git.git_clone(
                        url=self.data.url,
                        destination=repo_path,
                        shallow=False,
                        env=environment,
                        logger=self._logger,
                    )

                    if self.data.ref:
                        self.info('ref', self.data.ref, 'green')
                        self.run(Command('git', 'checkout', '-f', self.data.ref), cwd=repo_path)

            guest.push(
                source=repo_path,
                destination=repo_path,
                options=["-s", "-p", "--chmod=755"],
            )

        return repo_path

    def _execute_scripts_regular(
        self,
        guest: Guest,
        logger: tmt.log.Logger,
        workdir: tmt.utils.Path,
        environment: tmt.utils.Environment,
    ) -> None:
        """Execute scripts on regular (non-bootc) guests"""
        prepare_wrapper_filename = safe_filename(PREPARE_WRAPPER_FILENAME, self, guest)
        prepare_wrapper_path = workdir / prepare_wrapper_filename
        logger.debug('prepare wrapper', prepare_wrapper_path, level=3)

        if self.data.url:
            repo_path = self._handle_git_repository(guest, workdir, environment)
            environment[self._cloned_repo_path_envvar_name] = EnvVarValue(repo_path.resolve())

        # Execute each script on the guest (with default shell options)
        for script in self.data.script:
            logger.verbose('script', script, 'green')
            script_with_options = tmt.utils.ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')
            self.write(prepare_wrapper_path, str(script_with_options), 'w')
            if not self.is_dry_run:
                prepare_wrapper_path.chmod(0o755)
            guest.push(
                source=prepare_wrapper_path,
                destination=prepare_wrapper_path,
                options=["-s", "-p", "--chmod=755"],
            )
            command: ShellScript
            if guest.become and not guest.facts.is_superuser:
                command = tmt.utils.ShellScript(f'sudo -E {prepare_wrapper_path}')
            else:
                command = tmt.utils.ShellScript(f'{prepare_wrapper_path}')
            guest.execute(command=command, cwd=workdir, env=environment)

    def _execute_scripts_bootc(
        self,
        guest: Guest,
        logger: tmt.log.Logger,
        workdir: tmt.utils.Path,
        environment: tmt.utils.Environment,
    ) -> None:
        """Execute scripts on bootc image mode guests using containerfile directives"""
        assert isinstance(guest.package_manager, Bootc)
        bootc_manager = cast(Bootc, guest.package_manager)

        # Handle git repository cloning for bootc mode
        if self.data.url:
            repo_path = self._handle_git_repository(guest, workdir, environment)

            # Add COPY directive for the repository
            # Even though /var/tmp is mounted as a volume, we still need to copy the repository
            # in the containerfile, to be able to interact with it during the build.
            relative_repo_path = repo_path.relative_to(workdir)
            bootc_manager.copy(str(relative_repo_path), str(repo_path), no_build=True)  # pyright: ignore[reportAttributeAccessIssue]

            bootc_manager.env(self._cloned_repo_path_envvar_name, str(repo_path), no_build=True)  # pyright: ignore[reportAttributeAccessIssue]
            environment[self._cloned_repo_path_envvar_name] = EnvVarValue(repo_path.resolve())

        # Add each script as a RUN directive in the containerfile
        for script in self.data.script:
            logger.verbose('script', script, 'green')
            script_with_options = tmt.utils.ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')

            bootc_manager.run_command(str(script_with_options), no_build=True)  # pyright: ignore[reportAttributeAccessIssue]

        if not self.is_dry_run:
            bootc_manager.build_container(workdir, environment)  # pyright: ignore[reportAttributeAccessIssue]

    def go(
        self,
        *,
        guest: 'Guest',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> tmt.steps.PluginOutcome:
        """
        Prepare the guests
        """

        outcome = super().go(guest=guest, environment=environment, logger=logger)

        environment = environment or tmt.utils.Environment()

        # Give a short summary
        overview = fmf.utils.listed(self.data.script, 'script')
        logger.info('overview', f'{overview} found', 'green')

        workdir = self.step.plan.worktree
        assert workdir is not None  # narrow type

        if not self.is_dry_run:
            topology = tmt.steps.Topology(self.step.plan.provision.ready_guests)
            topology.guest = tmt.steps.GuestTopology(guest)

            environment.update(
                topology.push(
                    dirpath=workdir,
                    guest=guest,
                    logger=logger,
                    filename_base=safe_filename(
                        tmt.steps.TEST_TOPOLOGY_FILENAME_BASE, self, guest
                    ),
                )
            )

        # Check if the guest is in bootc mode
        # Do not use guest.package_manager.NAME,
        # as it may produce false positive at this step.
        bootc_mode = False
        try:
            output = guest.execute(Bootc.probe_command)
            if output.stdout is not None and output.stderr is not None:
                bootc_mode = True
        except Exception:
            logger.debug('bootc mode not detected', level=3)

        # Handle bootc image mode
        if bootc_mode:
            self._execute_scripts_bootc(guest, logger, workdir, environment)
        else:
            self._execute_scripts_regular(guest, logger, workdir, environment)

        return outcome
