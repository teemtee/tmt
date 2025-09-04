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
from tmt.steps import safe_filename
from tmt.steps.provision import Guest, TransferOptions
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

        environment.update(guest.environment)

        # Give a short summary
        overview = fmf.utils.listed(self.data.script, 'script')
        logger.info('overview', f'{overview} found', 'green')

        worktree = self.step.plan.worktree
        assert worktree is not None  # narrow type

        if self.data.url:
            assert self.workdir is not None  # narrow type

            repo_path = self.workdir / "repository"

            environment[self._cloned_repo_path_envvar_name] = EnvVarValue(repo_path.resolve())

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
                            self.run(
                                Command('git', 'checkout', '-f', self.data.ref), cwd=repo_path
                            )

                guest.push(
                    source=repo_path,
                    destination=repo_path,
                    options=TransferOptions(protect_args=True, preserve_perms=True, chmod=0o755),
                )

        if not self.is_dry_run:
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

        prepare_wrapper_filename = safe_filename(PREPARE_WRAPPER_FILENAME, self, guest)
        prepare_wrapper_path = worktree / prepare_wrapper_filename

        logger.debug('prepare wrapper', prepare_wrapper_path, level=3)

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
                options=TransferOptions(protect_args=True, preserve_perms=True, chmod=0o755),
            )
            command: ShellScript
            if guest.become and not guest.facts.is_superuser:
                command = tmt.utils.ShellScript(f'sudo -E {prepare_wrapper_path}')
            else:
                command = tmt.utils.ShellScript(f'{prepare_wrapper_path}')
            guest.execute(command=command, cwd=worktree, env=environment)

        return outcome
