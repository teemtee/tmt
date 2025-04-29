from typing import Any, Optional

import tmt.log
from tmt.container import container, field
from tmt.steps.prepare.feature import Feature, PrepareFeatureData, provides_feature
from tmt.steps.provision import AnsibleCollectionPlaybook, Guest

# TODO: provide link to said specification once it's created.
#: The name of a playbook provided by the collection. This name is
#: part of the Testing Farm profile specification.
PLAYBOOK_NAME = 'apply'


@container
class ProfileStepData(PrepareFeatureData):
    profile: Optional[str] = field(
        default=None,
        option='--profile',
        metavar='NAME',
        help='Apply guest profile.',
    )


@provides_feature('profile')
class Profile(Feature):
    """
    Prepare guest setup with a guest profile.

    .. note::

        Guest profiles are being developed, once there is an agreed upon
        text we could steal^Wborrow^Wreuse, we shall add it to this
        docstring.

    Guest profiles represent a particular setup of guest environment as
    defined by a CI system or service. They are implemented as Ansible
    roles, and packaged as Ansible collections. The CI systems use
    profiles to set up guests before testing, and users may use the same
    profiles to establish the same environment locally when developing
    tests or reprodcing issues.

    Apply a profile to the guest:

    .. code-block:: yaml

        prepare:
            how: feature
            profile: testing_farm.fedora_ci

    .. code-block:: shell

        prepare --how feature --profile testing_farm.fedora_ci
    """

    NAME = "profile"

    _data_class = ProfileStepData

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def enable(cls, guest: Guest, value: str, logger: tmt.log.Logger) -> None:
        logger.info('Guest profile', value)

        guest.ansible(AnsibleCollectionPlaybook(f'{value}.{PLAYBOOK_NAME}'))
