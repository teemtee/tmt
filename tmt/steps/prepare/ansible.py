import dataclasses
import tempfile
from typing import Optional, Union

import requests

import tmt
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.steps.provision import Guest
from tmt.utils import Path, PrepareError, field, retry_session


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
        playbook = raw_data.pop('playbook', [])
        if isinstance(playbook, str):
            playbook = [playbook]
        elif isinstance(playbook, tuple):
            playbook = list(playbook)
        assert isinstance(playbook, list)
        raw_data['playbook'] = playbook

        raw_data['playbook'] += raw_data.pop('playbooks', [])


@tmt.steps.provides_method('ansible')
class PrepareAnsible(tmt.steps.prepare.PreparePlugin[PrepareAnsibleData]):
    """
    Prepare guest using Ansible.

    Run Ansible playbooks against the guest, by running
    ``ansible-playbook`` for all given playbooks.

    .. warning::

        When specifying playbooks with paths, all paths must be
        relative to the metadata tree root.

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

    Remote playbooks can be referenced as well as local ones, and both
    kinds can be intermixed:

    .. code-block:: yaml

        prepare:
            how: ansible
            playbook:
              - https://foo.bar/one.yml
              - two.yml

    .. code-block:: shell

        prepare --how ansible --playbook https://foo.bar/two.yml --playbook two.yml
    """

    _data_class = PrepareAnsibleData

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> None:
        """ Prepare the guests """
        super().go(guest=guest, environment=environment, logger=logger)

        # Apply each playbook on the guest
        for playbook in self.data.playbook:
            logger.info('playbook', playbook, 'green')

            lowercased_playbook = playbook.lower()
            playbook_path = Path(playbook)

            if lowercased_playbook.startswith(('http://', 'https://')):
                assert self.step.plan.my_run is not None  # narrow type
                assert self.step.plan.my_run.tree is not None  # narrow type
                assert self.step.plan.my_run.tree.root is not None  # narrow type
                root_path = self.step.plan.my_run.tree.root

                try:
                    with retry_session() as session:
                        response = session.get(playbook)

                    if not response.ok:
                        raise PrepareError(
                            f"Failed to fetch remote playbook '{playbook}'.")

                except requests.RequestException as exc:
                    raise PrepareError(
                        f"Failed to fetch remote playbook '{playbook}'.") from exc

                with tempfile.NamedTemporaryFile(
                        mode='w+b',
                        prefix='playbook-',
                        suffix='.yml',
                        dir=root_path,
                        delete=False) as file:
                    file.write(response.content)
                    file.flush()

                    playbook_path = Path(file.name).relative_to(root_path)

                logger.info('playbook-path', playbook_path, 'green')

            guest.ansible(playbook_path, extra_args=self.data.extra_args)
