import dataclasses
import tempfile
from typing import Optional, Union

import requests

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.steps.provision
import tmt.utils
from tmt.result import PhaseResult
from tmt.steps.provision import (
    ANSIBLE_COLLECTION_PLAYBOOK_PATTERN,
    AnsibleApplicable,
    AnsibleCollectionPlaybook,
    Guest,
    )
from tmt.utils import (
    DEFAULT_RETRIABLE_HTTP_CODES,
    ENVFILE_RETRY_SESSION_RETRIES,
    Path,
    PrepareError,
    field,
    normalize_string_list,
    retry_session,
    )


class _RawAnsibleStepData(tmt.steps._RawStepData, total=False):
    playbook: Union[str, list[str]]
    playbooks: list[str]


@dataclasses.dataclass
class PrepareAnsibleData(tmt.steps.prepare.PrepareStepData):
    playbook: list[str] = field(
        default_factory=list,
        option=('-p', '--playbook'),
        multiple=True,
        metavar='PATH|URL',
        help="""
             Path or URL of an ansible playbook to run.
             The playbook path must be relative to the metadata tree root.
             """,
        normalize=tmt.utils.normalize_string_list
        )

    extra_args: Optional[str] = field(
        default=None,
        option='--extra-args',
        metavar='ANSIBLE-PLAYBOOK-OPTIONS',
        help='Additional CLI options for ``ansible-playbook``.'
        )

    # ignore[override]: method violates a liskov substitution principle,
    # but only apparently.  Thanks to how tmt initializes module, we can
    # safely assume PrepareAnsibleData.pre_normalization() would be
    # called with source data matching _RawAnsibleStepData.
    @classmethod
    def pre_normalization(  # type: ignore[override]
            cls,
            raw_data: _RawAnsibleStepData,
            logger: tmt.log.Logger) -> None:
        super().pre_normalization(raw_data, logger)

        # Perform `playbook` normalization here, so we could merge `playbooks` to it.
        playbook = normalize_string_list('playbook', raw_data.pop('playbook', []), logger)
        playbooks = normalize_string_list('playbook', raw_data.pop('playbooks', []), logger)

        raw_data['playbook'] = [*playbook, *playbooks]


@tmt.steps.provides_method('ansible')
class PrepareAnsible(tmt.steps.prepare.PreparePlugin[PrepareAnsibleData]):
    """
    Prepare guest using Ansible.

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

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[PhaseResult]:
        """ Prepare the guests """
        results = super().go(guest=guest, environment=environment, logger=logger)

        # Apply each playbook on the guest
        for _playbook in self.data.playbook:
            logger.info('playbook', _playbook, 'green')

            lowercased_playbook = _playbook.lower()

            def normalize_remote_playbook(raw_playbook: str) -> Path:
                assert self.step.plan.my_run is not None  # narrow type
                assert self.step.plan.my_run.tree is not None  # narrow type
                assert self.step.plan.my_run.tree.root is not None  # narrow type
                root_path = self.step.plan.my_run.tree.root

                try:
                    with retry_session(
                            retries=ENVFILE_RETRY_SESSION_RETRIES,
                            status_forcelist=DEFAULT_RETRIABLE_HTTP_CODES) as session:
                        response = session.get(raw_playbook)

                    if not response.ok:
                        raise PrepareError(
                            f"Failed to fetch remote playbook '{raw_playbook}'.")

                except requests.RequestException as exc:
                    raise PrepareError(
                        f"Failed to fetch remote playbook '{raw_playbook}'.") from exc

                with tempfile.NamedTemporaryFile(
                        mode='w+b',
                        prefix='playbook-',
                        suffix='.yml',
                        dir=root_path,
                        delete=False) as file:
                    file.write(response.content)
                    file.flush()

                    return Path(file.name).relative_to(root_path)

            def normalize_local_playbook(raw_playbook: str) -> Path:
                if raw_playbook.startswith('file://'):
                    return Path(raw_playbook[7:])

                return Path(raw_playbook)

            def normalize_collection_playbook(raw_playbook: str) -> AnsibleCollectionPlaybook:
                return AnsibleCollectionPlaybook(raw_playbook)

            playbook: AnsibleApplicable

            if lowercased_playbook.startswith(('http://', 'https://')):
                playbook = normalize_remote_playbook(lowercased_playbook)

            elif lowercased_playbook.startswith('file://'):
                playbook = normalize_local_playbook(lowercased_playbook)

            elif ANSIBLE_COLLECTION_PLAYBOOK_PATTERN.match(lowercased_playbook):
                playbook = normalize_collection_playbook(lowercased_playbook)

            else:
                playbook = normalize_local_playbook(lowercased_playbook)

            guest.ansible(
                playbook,
                playbook_root=self.step.plan.anchor_path,
                extra_args=self.data.extra_args)

        return results

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return tmt.steps.provision.essential_ansible_requires()
