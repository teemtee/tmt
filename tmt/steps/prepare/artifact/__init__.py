from typing import Optional

import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.log import Logger
from tmt.steps import PluginOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.steps.provision import Guest
from tmt.utils import Environment


@container
class PrepareArtifactData(PrepareStepData):
    provide: list[str] = field(
        default_factory=list,
        option='--provide',
        metavar='ID',
        help='Artifact ID to provide. Format <type>:<id>.',
        multiple=True,
        normalize=tmt.utils.normalize_string_list,
    )


@tmt.steps.provides_method('artifact')
class PrepareArtifact(PreparePlugin[PrepareArtifactData]):
    """
    Prepare artifacts on the guest.

    .. note::

       This is a draft plugin to be implemented
    """

    _data_class = PrepareArtifactData

    def go(
        self,
        *,
        guest: Guest,
        environment: Optional[Environment] = None,
        logger: Logger,
    ) -> PluginOutcome:
        outcome = super().go(guest=guest, environment=environment, logger=logger)
        # TODO: Implementation
        raise NotImplementedError
        return outcome
