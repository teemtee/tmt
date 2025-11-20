import threading
from typing import Any, Optional, cast

import fmf
import fmf.utils

import tmt
import tmt.log
import tmt.steps
import tmt.steps.context.pidfile
import tmt.steps.context.reboot
import tmt.steps.prepare
import tmt.utils
import tmt.utils.git
from tmt.container import container, field
from tmt.steps import safe_filename
from tmt.steps.provision import DEFAULT_PULL_OPTIONS, Guest, TransferOptions
from tmt.utils import Command, EnvVarValue, ShellScript, Stopwatch

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
            running any scripts, the path on the guest will be stored in
            a step variable.
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
    """

    _data_class = PrepareShellData
    _url_clone_lock = threading.Lock()
    _cloned_repo_path_envvar_name = 'TMT_PREPARE_SHELL_URL_REPOSITORY'

    @property
    def _preserved_workdir_members(self) -> set[str]:
        return {
            *super()._preserved_workdir_members,
            # Include directories storing individual scriptlogs.
            *{f'script-{i}' for i in range(len(self.data.script))},
        }

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

        reboot_context = tmt.steps.context.reboot.RebootContext(
            owner_label=f'{self.step.name} / {self.name}',
            guest=guest,
            path=self.phase_workdir,
            logger=logger,
        )

        pidfile_context = tmt.steps.context.pidfile.PidFileContext(
            phase=self, guest=guest, logger=logger
        )

        environment = environment or tmt.utils.Environment()
        environment.update(guest.environment)

        # Give a short summary
        overview = fmf.utils.listed(self.data.script, 'script')
        logger.info('overview', f'{overview} found', 'green')

        worktree = self.step.plan.worktree
        assert worktree is not None  # narrow type

        def _prepare_remote_repository() -> None:
            if not self.data.url:
                return

            repo_path = self.phase_workdir / "repository"

            environment[self._cloned_repo_path_envvar_name] = EnvVarValue(repo_path.resolve())

            if self.is_dry_run:
                return

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
                options=TransferOptions(
                    protect_args=True,
                    preserve_perms=True,
                    chmod=0o755,
                    recursive=True,
                    create_destination=True,
                ),
            )

        _, error, timer = Stopwatch.measure(_prepare_remote_repository)

        if error is not None:
            return self._save_error_outcome(
                label=f'{self.name} / remote script repository',
                timer=timer,
                guest=guest,
                exception=error,
                outcome=outcome,
            )

        def _prepare_topology() -> None:
            if self.is_dry_run:
                return

            topology = tmt.steps.Topology(self.step.plan.provision.ready_guests)
            topology.guest = tmt.steps.GuestTopology(guest)

            environment.update(
                topology.push(
                    dirpath=worktree,
                    guest=guest,
                    logger=logger,
                    filename_base=safe_filename(
                        tmt.steps.TEST_TOPOLOGY_FILENAME_BASE, self, guest
                    ),
                )
            )

        _, error, timer = Stopwatch.measure(_prepare_topology)

        if error is not None:
            return self._save_error_outcome(
                label=f'{self.name} / guest topology',
                timer=timer,
                guest=guest,
                exception=error,
                outcome=outcome,
            )

        def _invoke_script(
            command: Command,
            environment: tmt.utils.Environment,
        ) -> tmt.utils.CommandOutput:
            guest.push(source=self.phase_workdir)

            return guest.execute(
                command=command,
                cwd=worktree,
                env=environment,
                sourced_files=[self.step.plan.plan_source_script],
            )

        script_queue = self.data.script[:]
        script_count = len(script_queue)

        while script_queue:
            script_index = len(script_queue) - script_count + 1
            script = original_script = script_queue.pop(0)

            logger.verbose('script', script, 'green')

            script_name = f'{self.name} / script #{script_index}'

            script_record_dirpath = self.phase_workdir / f'script-{script_index}' / guest.safe_name
            script_log_filepath = script_record_dirpath / 'output.txt'

            script_log_filepath.parent.mkdir(parents=True, exist_ok=True)
            script_log_filepath.touch()

            script_environment = environment.copy()
            script_environment.update(reboot_context)
            script_environment.update(pidfile_context)

            pull_options = DEFAULT_PULL_OPTIONS.copy()
            pull_options.exclude.append(str(script_log_filepath))

            if guest.become and not guest.facts.is_superuser:
                script = ShellScript(f'{guest.facts.sudo_prefix} {script.to_shell_command()}')

            script = ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')

            _, outer_wrapper_filepath = pidfile_context.create_wrappers(
                worktree,
                f'inner-{PREPARE_WRAPPER_FILENAME}',
                f'outer-{PREPARE_WRAPPER_FILENAME}',
                ACTION=script,
            )

            output, error, timer = Stopwatch.measure(
                _invoke_script,
                Command(outer_wrapper_filepath),
                script_environment,
            )

            if error is not None:
                if isinstance(error, tmt.utils.RunError):
                    self._post_action_pull(
                        guest=guest,
                        path=self.phase_workdir,
                        pull_options=pull_options,
                        reboot=reboot_context,
                        exceptions=outcome.exceptions,
                    )

                if reboot_context.requested and reboot_context.handle_reboot():
                    self.write_command_report(
                        path=script_log_filepath,
                        label=script_name,
                        timer=timer,
                        command=script,
                        exc=error,
                    )

                    script_queue.insert(0, original_script)

                    continue

                return self._save_failed_run_outcome(
                    log_filepath=script_log_filepath,
                    label=script_name,
                    timer=timer,
                    guest=guest,
                    command=script,
                    exception=error,
                    outcome=outcome,
                )

            if output is None:
                return self._save_error_outcome(
                    label=script_name,
                    timer=timer,
                    note='Command produced no output but raised no exception',
                    guest=guest,
                    outcome=outcome,
                )

            self._post_action_pull(
                guest=guest,
                path=self.phase_workdir,
                pull_options=pull_options,
                reboot=reboot_context,
                exceptions=outcome.exceptions,
            )

            self._save_success_outcome(
                log_filepath=script_log_filepath,
                label=script_name,
                timer=timer,
                guest=guest,
                output=output,
                outcome=outcome,
            )

        return outcome
