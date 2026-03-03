import tempfile
import uuid
from typing import Optional, Union, cast

import requests

import tmt
import tmt.base
import tmt.guest
import tmt.log
import tmt.package_managers.bootc
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.container import container, field
from tmt.guest import (
    ANSIBLE_COLLECTION_PLAYBOOK_PATTERN,
    AnsibleApplicable,
    AnsibleCollectionPlaybook,
    CommandCollector,
    Guest,
    TransferOptions,
)
from tmt.package_managers import Package
from tmt.package_managers.bootc import LOCALHOST_BOOTC_IMAGE_PREFIX
from tmt.utils import (
    Command,
    Path,
    PrepareError,
    ShellScript,
    Stopwatch,
    normalize_string_list,
    retry_session,
)


class _RawAnsibleStepData(tmt.steps._RawStepData, total=False):
    playbook: Union[str, list[str]]
    playbooks: list[str]


@container
class PrepareAnsibleData(tmt.steps.prepare.PrepareStepData):
    playbook: list[str] = field(
        default_factory=list,
        option=('-p', '--playbook'),
        multiple=True,
        metavar='PATH|URL|NAMESPACE.COLLECTION.PLAYBOOK',
        help="""
             Path or URL of an Ansible playbook, or a playbook
             bundled within a collection, to run on a guest.
             Playbook ``PATH`` must be relative to the metadata tree
             root, if the metadata tree exists, or to the current
             working directory.
             """,
        normalize=tmt.utils.normalize_string_list,
    )

    extra_args: Optional[str] = field(
        default=None,
        option='--extra-args',
        metavar='ANSIBLE-PLAYBOOK-OPTIONS',
        help='Additional CLI options for ``ansible-playbook``.',
        help_example_values=['-vvv'],
    )

    # ignore[override]: method violates a liskov substitution principle,
    # but only apparently.  Thanks to how tmt initializes module, we can
    # safely assume PrepareAnsibleData.pre_normalization() would be
    # called with source data matching _RawAnsibleStepData.
    @classmethod
    def pre_normalization(  # type: ignore[override]
        cls, raw_data: _RawAnsibleStepData, logger: tmt.log.Logger
    ) -> None:
        super().pre_normalization(raw_data, logger)

        # Perform `playbook` normalization here, so we could merge `playbooks` to it.
        playbook = normalize_string_list('playbook', raw_data.pop('playbook', []), logger)
        playbooks = normalize_string_list('playbook', raw_data.pop('playbooks', []), logger)

        raw_data['playbook'] = [*playbook, *playbooks]


@tmt.steps.provides_method('ansible')
class PrepareAnsible(tmt.steps.prepare.PreparePlugin[PrepareAnsibleData]):
    #
    # This plugin docstring has been reviewed and updated to follow
    # our documentation best practices. When changing it, please make
    # sure new changes are following them as well.
    #
    # https://tmt.readthedocs.io/en/stable/contribute.html#docs
    #
    """
    Run Ansible playbooks against the guest, by running
    ``ansible-playbook`` for all given playbooks.

    .. note::

       The plugin requires a working Ansible to be available on the
       test runner.

    .. warning::

        When specifying playbooks with paths:

        * If a metadata tree root exists, all paths must be relative to
          the metadata tree root.
        * If the metadata tree root does not exist,
          all paths must be relative to the current working directory.

    .. warning::

       The plugin may be a subject of various limitations, imposed by
       Ansible itself:

       * Ansible 2.17+ no longer supports Python 3.6 and older. Guests
         where Python 3.7+ is not available cannot be prepared with the
         ``ansible`` plugin. This has been observed when Fedora Rawhide
         runner is used with CentOS 7 or CentOS Stream 8 guests. Possible
         workarounds: downgrade Ansible tmt uses, or install Python 3.7+
         before using ``ansible`` plugin from an alternative repository
         or local build.

    Run a single playbook on the guest:

    .. code-block:: yaml

        prepare:
            how: ansible
            playbook: ansible/packages.yml

    .. code-block:: shell

        prepare --how ansible --playbook ansible/packages.yml

    Run multiple playbooks in one phase, with extra arguments for
    ``ansible-playbook``:

    .. code-block:: yaml

        prepare:
            how: ansible
            playbook:
              - one.yml
              - two.yml
            extra-args: '-vvv'

    .. code-block:: shell

        prepare --how ansible --playbook one.yml --playbook two.yml --extra-args '-vvv'

    Remote playbooks - provided as URLs starting with ``http://`` or
    ``https://``, local playbooks - optionally starting with a
    ``file://`` schema, and playbooks bundled with collections can be
    referenced as well as local ones, and all kinds can be intermixed:

    .. code-block:: yaml

        prepare:
            how: ansible
            playbook:
              - https://foo.bar/one.yml
              - two.yml
              - file://three.yml
              - ansible_galaxy_namespace.cool_collection.four

    .. code-block:: shell

        prepare --how ansible --playbook https://foo.bar/two.yml \\
                              --playbook two.yml \\
                              --playbook file://three.yml \\
                              --playbook ansible_galaxy_namespace.cool_collection.four
    """

    _data_class = PrepareAnsibleData

    @property
    def _preserved_workdir_members(self) -> set[str]:
        return {
            *super()._preserved_workdir_members,
            # Include directories storing individual playbook logs.
            *{f'playbook-{i}' for i in range(len(self.data.playbook))},
        }

    def _ensure_ansible_on_guest(
        self,
        guest: 'Guest',
        logger: tmt.log.Logger,
    ) -> None:
        """
        Ensure ansible-playbook is available on the guest.

        Checks if ansible-playbook is already installed. If not, installs
        ansible-core via the bootc package manager, which triggers a
        container image build, bootc switch, and reboot.
        """

        try:
            guest.execute(Command('which', 'ansible-playbook'), silent=True)
            logger.debug('ansible-playbook is already available on the guest.')
        except tmt.utils.RunError:
            logger.info('ansible', 'installing ansible-core on the guest', 'green')
            guest.package_manager.install(Package('ansible-core'))

    def _resolve_playbook_for_guest(
        self,
        raw_playbook: str,
        playbook_index: int,
        guest: 'Guest',
        logger: tmt.log.Logger,
    ) -> str:
        """
        Resolve a playbook specification and push it to the guest.

        Handles local files, URLs, and collection playbooks.
        Returns the guest-side path (or collection reference) for
        ansible-playbook.

        :param playbook_index: used to create unique destination filenames
            on the guest, preventing collisions when multiple playbooks
            share the same filename.
        """

        # Use non-recursive, non-relative options for pushing individual
        # files. The default push options use recursive=True and
        # relative=True which causes rsync to place the file at a deeply
        # nested path (preserving the full source directory structure)
        # instead of the intended destination.
        file_push_options = TransferOptions(
            protect_args=True,
            compress=True,
        )

        lowercased = raw_playbook.lower()

        if lowercased.startswith(('http://', 'https://')):
            # Download remote playbook to step workdir and push to guest
            try:
                with retry_session(logger=logger) as session:
                    response = session.get(raw_playbook)

                if not response.ok:
                    raise PrepareError(f"Failed to fetch remote playbook '{raw_playbook}'.")

            except requests.RequestException as error:
                raise PrepareError(f"Failed to fetch remote playbook '{raw_playbook}'.") from error

            with tempfile.NamedTemporaryFile(
                mode='w+b',
                prefix='playbook-',
                suffix='.yml',
                dir=self.step_workdir,
                delete=False,
            ) as file:
                file.write(response.content)
                file.flush()

                local_path = Path(file.name)
                guest_path = guest.run_workdir / local_path.name
                guest.push(
                    source=local_path,
                    destination=guest_path,
                    options=file_push_options,
                )
                return str(guest_path)

        if ANSIBLE_COLLECTION_PLAYBOOK_PATTERN.match(lowercased):
            # Collection playbooks are referenced by name, no file to push
            return raw_playbook

        # Local playbook file — use playbook_index prefix to avoid
        # filename collisions (e.g. dir1/setup.yml vs dir2/setup.yml)
        if lowercased.startswith('file://'):
            rel_path = Path(raw_playbook[7:])
        else:
            rel_path = Path(raw_playbook)

        local_path = self.step.plan.anchor_path / rel_path
        guest_filename = f'{playbook_index}-{rel_path.name}'
        guest_path = guest.run_workdir / guest_filename
        guest.push(
            source=local_path,
            destination=guest_path,
            options=file_push_options,
        )
        return str(guest_path)

    def _go_image_mode(
        self,
        *,
        guest: 'Guest',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
        outcome: tmt.steps.PluginOutcome,
    ) -> tmt.steps.PluginOutcome:
        """
        Run ansible playbooks on an image mode (bootc) guest.

        Starts a container from the current bootc image on the guest,
        runs ansible-playbook with the podman connection plugin targeting
        the container, commits the container to a new image, switches
        via bootc switch, and reboots.
        """

        bootc_pm = cast(tmt.package_managers.bootc.Bootc, guest.package_manager)

        assert isinstance(bootc_pm.engine, tmt.package_managers.bootc.BootcEngine)
        bootc_engine = bootc_pm.engine

        # Flush any pending containerfile directives from prior
        # shell/install phases to ensure correct image layering
        if isinstance(guest, CommandCollector) and guest.has_collected_commands:
            guest.flush_collected()

        # Ensure ansible-playbook is available on the guest
        self._ensure_ansible_on_guest(guest, logger)

        # Get current bootc image
        current_image = bootc_engine._get_current_bootc_image()
        container_name = f'tmt-ansible-prepare-{uuid.uuid4()}'
        new_image_tag = f'{LOCALHOST_BOOTC_IMAGE_PREFIX}/bootc/{uuid.uuid4()}'

        assert guest.facts.sudo_prefix is not None  # narrow type

        try:
            # Ensure the image is available in podman's container storage.
            # The bootc image may only exist in ostree storage and not be
            # pullable from a registry, so we need the same fallback logic
            # as build_container(): try pulling, then copy from bootc.
            if not current_image.startswith(LOCALHOST_BOOTC_IMAGE_PREFIX):
                logger.debug(f'Ensuring image {current_image} is in podman storage.')
                guest.execute(
                    ShellScript(
                        f'{guest.facts.sudo_prefix} /bin/bash -c "('
                        f'  ( podman pull {current_image}'
                        f'    || podman pull containers-storage:{current_image} )'
                        f'  || bootc image copy-to-storage --target {current_image}'
                        ')"'
                    )
                )

            # Start a container from the current bootc image
            logger.info('ansible', f'starting container {container_name}', 'green')
            guest.execute(
                ShellScript(
                    f'{guest.facts.sudo_prefix} podman run -d'
                    f' --name {container_name}'
                    f' -v {guest.run_workdir}:{guest.run_workdir}:Z'
                    f' {current_image}'
                    f' sleep infinity'
                )
            )

            # Run each playbook against the container
            for playbook_index, _playbook in enumerate(self.data.playbook):
                logger.info('playbook', _playbook, 'green')

                playbook_name = f'{self.name} / {_playbook}'

                playbook_record_dirpath = (
                    self.phase_workdir / f'playbook-{playbook_index}' / guest.safe_name
                )
                playbook_log_filepath = playbook_record_dirpath / 'output.txt'

                def invoke_playbook_image_mode(
                    playbook_record_dirpath: Path,
                    raw_playbook: str,
                    pb_index: int,
                ) -> tmt.utils.CommandOutput:
                    playbook_record_dirpath.mkdir(parents=True, exist_ok=True)

                    guest_playbook = self._resolve_playbook_for_guest(
                        raw_playbook, pb_index, guest, logger
                    )

                    # Build the ansible-playbook command to run on the guest
                    ansible_cmd = (
                        f'{guest.facts.sudo_prefix} ansible-playbook'
                        f' -c containers.podman.podman'
                        f" -i '{container_name},'"
                        f' {guest_playbook}'
                    )

                    if self.data.extra_args:
                        ansible_cmd += f' {self.data.extra_args}'

                    return guest.execute(ShellScript(ansible_cmd))

                output, exc, timer = Stopwatch.measure(
                    invoke_playbook_image_mode, playbook_record_dirpath, _playbook, playbook_index
                )

                if exc is not None:
                    return self._save_failed_run_outcome(
                        log_filepath=playbook_log_filepath,
                        label=playbook_name,
                        timer=timer,
                        guest=guest,
                        exception=exc,
                        outcome=outcome,
                    )

                if output is None:
                    return self._save_error_outcome(
                        label=playbook_name,
                        timer=timer,
                        note='Command produced no output but raised no exception',
                        guest=guest,
                        outcome=outcome,
                    )

                self._save_success_outcome(
                    log_filepath=playbook_log_filepath,
                    label=playbook_name,
                    timer=timer,
                    guest=guest,
                    output=output,
                    outcome=outcome,
                )

            # Commit the container to a new image
            logger.info('ansible', f'committing container to {new_image_tag}', 'green')
            guest.execute(
                ShellScript(
                    f'{guest.facts.sudo_prefix} podman commit {container_name} {new_image_tag}'
                )
            )

            # Switch to the new image
            logger.info('ansible', f'switching to new image {new_image_tag}', 'green')
            bootc_command, _ = bootc_engine.prepare_command()
            bootc_command += Command('switch', '--transport', 'containers-storage', new_image_tag)
            guest.execute(bootc_command)

            # Reboot into the new image
            logger.info('ansible', 'rebooting to apply new image', 'green')
            guest.reboot()

        finally:
            # Cleanup the container. After a successful reboot the
            # container no longer exists, so failure is expected.
            # Catch broadly to avoid masking the original exception.
            try:
                guest.execute(
                    ShellScript(f'{guest.facts.sudo_prefix} podman rm -f {container_name}')
                )
            except Exception:
                logger.debug(f'Failed to remove container {container_name}.')

        return outcome

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

        # Delegate to image mode handler for bootc guests
        if guest.facts.is_image_mode and isinstance(
            guest.package_manager, tmt.package_managers.bootc.Bootc
        ):
            return self._go_image_mode(
                guest=guest, environment=environment, logger=logger, outcome=outcome
            )

        # Apply each playbook on the guest
        for playbook_index, _playbook in enumerate(self.data.playbook):
            logger.info('playbook', _playbook, 'green')

            playbook_name = f'{self.name} / {_playbook}'
            lowercased_playbook = _playbook.lower()

            playbook_record_dirpath = (
                self.phase_workdir / f'playbook-{playbook_index}' / guest.safe_name
            )
            playbook_log_filepath = playbook_record_dirpath / 'output.txt'

            def normalize_remote_playbook(raw_playbook: str) -> tuple[Path, AnsibleApplicable]:
                root_path = self.step_workdir

                try:
                    with retry_session(logger=logger) as session:
                        response = session.get(raw_playbook)

                    if not response.ok:
                        raise PrepareError(f"Failed to fetch remote playbook '{raw_playbook}'.")

                except requests.RequestException as error:
                    raise PrepareError(
                        f"Failed to fetch remote playbook '{raw_playbook}'."
                    ) from error

                with tempfile.NamedTemporaryFile(
                    mode='w+b',
                    prefix='playbook-',
                    suffix='.yml',
                    dir=root_path,
                    delete=False,
                ) as file:
                    file.write(response.content)
                    file.flush()

                    return root_path, Path(file.name).relative_to(root_path)

            def normalize_local_playbook(raw_playbook: str) -> tuple[Path, AnsibleApplicable]:
                if raw_playbook.startswith('file://'):
                    return self.step.plan.anchor_path, Path(raw_playbook[7:])

                return self.step.plan.anchor_path, Path(raw_playbook)

            def normalize_collection_playbook(raw_playbook: str) -> tuple[Path, AnsibleApplicable]:
                return self.step.plan.anchor_path, AnsibleCollectionPlaybook(raw_playbook)

            def invoke_playbook(
                playbook_record_dirpath: Path, lowercased_playbook: str
            ) -> tmt.utils.CommandOutput:
                playbook_record_dirpath.mkdir(parents=True, exist_ok=True)

                if lowercased_playbook.startswith(('http://', 'https://')):
                    playbook_root, playbook = normalize_remote_playbook(lowercased_playbook)

                elif lowercased_playbook.startswith('file://'):
                    playbook_root, playbook = normalize_local_playbook(lowercased_playbook)

                elif ANSIBLE_COLLECTION_PLAYBOOK_PATTERN.match(lowercased_playbook):
                    playbook_root, playbook = normalize_collection_playbook(lowercased_playbook)

                else:
                    playbook_root, playbook = normalize_local_playbook(lowercased_playbook)

                return guest.run_ansible_playbook(
                    playbook,
                    playbook_root=playbook_root,
                    extra_args=self.data.extra_args,
                )

            output, exc, timer = Stopwatch.measure(
                invoke_playbook, playbook_record_dirpath, lowercased_playbook
            )

            if exc is not None:
                return self._save_failed_run_outcome(
                    log_filepath=playbook_log_filepath,
                    label=playbook_name,
                    timer=timer,
                    guest=guest,
                    exception=exc,
                    outcome=outcome,
                )

            if output is None:
                return self._save_error_outcome(
                    label=playbook_name,
                    timer=timer,
                    note='Command produced no output but raised no exception',
                    guest=guest,
                    outcome=outcome,
                )

            self._save_success_outcome(
                log_filepath=playbook_log_filepath,
                label=playbook_name,
                timer=timer,
                guest=guest,
                output=output,
                outcome=outcome,
            )

        return outcome

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return tmt.guest.essential_ansible_requires()
