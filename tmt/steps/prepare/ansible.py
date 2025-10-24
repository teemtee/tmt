import tempfile
from typing import Optional, Union

import requests

import tmt
import tmt.base
import tmt.log
import tmt.result
import tmt.steps
import tmt.steps.prepare
import tmt.steps.provision
import tmt.utils
from tmt.container import container, field
from tmt.result import ResultOutcome
from tmt.steps.provision import (
    ANSIBLE_COLLECTION_PLAYBOOK_PATTERN,
    AnsibleApplicable,
    AnsibleCollectionPlaybook,
    Guest,
)
from tmt.utils import (
    ENVFILE_RETRY_SESSION_RETRIES,
    Path,
    PrepareError,
    RunError,
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
                    with retry_session(
                        retries=ENVFILE_RETRY_SESSION_RETRIES, logger=logger
                    ) as session:
                        response = session.get(raw_playbook)

                    if not response.ok:
                        raise PrepareError(f"Failed to fetch remote playbook '{raw_playbook}'.")

                except requests.RequestException as exc:
                    raise PrepareError(
                        f"Failed to fetch remote playbook '{raw_playbook}'."
                    ) from exc

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

            try:
                playbook_record_dirpath.mkdir(parents=True, exist_ok=True)

                if lowercased_playbook.startswith(('http://', 'https://')):
                    playbook_root, playbook = normalize_remote_playbook(lowercased_playbook)

                elif lowercased_playbook.startswith('file://'):
                    playbook_root, playbook = normalize_local_playbook(lowercased_playbook)

                elif ANSIBLE_COLLECTION_PLAYBOOK_PATTERN.match(lowercased_playbook):
                    playbook_root, playbook = normalize_collection_playbook(lowercased_playbook)

                else:
                    playbook_root, playbook = normalize_local_playbook(lowercased_playbook)

                output = guest.run_ansible_playbook(
                    playbook,
                    playbook_root=playbook_root,
                    extra_args=self.data.extra_args,
                )

            except RunError as exc:
                self.write(
                    playbook_log_filepath,
                    '\n'.join(
                        tmt.utils.render_command_report(label=playbook_name, output=exc.output)
                    ),
                )

                outcome.results.append(
                    tmt.result.PhaseResult(
                        name=playbook_name,
                        result=ResultOutcome.FAIL,
                        note=tmt.utils.render_exception_as_notes(exc),
                        log=[playbook_log_filepath.relative_to(self.step_workdir)],
                    )
                )

                outcome.exceptions.append(exc)

                return outcome

            except Exception as exc:
                outcome.results.append(
                    tmt.result.PhaseResult(
                        name=playbook_name,
                        result=ResultOutcome.ERROR,
                        note=tmt.utils.render_exception_as_notes(exc),
                    )
                )

                outcome.exceptions.append(exc)

                return outcome

            else:
                self.write(
                    playbook_log_filepath,
                    '\n'.join(tmt.utils.render_command_report(label=playbook_name, output=output)),
                )

                outcome.results.append(
                    tmt.result.PhaseResult(
                        name=playbook_name,
                        result=ResultOutcome.PASS,
                        log=[playbook_log_filepath.relative_to(self.step_workdir)],
                    )
                )

        return outcome

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return tmt.steps.provision.essential_ansible_requires()
