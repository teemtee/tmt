from typing import Optional

import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.log import Logger
from tmt.steps import PluginOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.steps.prepare.artifact.providers import _PROVIDER_REGISTRY
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
        # TODO: Get and handle repositories
        # TODO: Create the local repository
        for raw_provider_id in self.data.provide:
            provider_type = raw_provider_id.split(':')[0]
            provider_class = _PROVIDER_REGISTRY.get_plugin(provider_type)
            if not provider_class:
                raise tmt.utils.PrepareError(f"Unknown provider type '{provider_type}'")
            provider_id_sanitized = tmt.utils.sanitize_name(raw_provider_id, allow_slash=False)
            logger = self._logger.descend(raw_provider_id)
            provider = provider_class(raw_provider_id, logger=logger)
            download_path = self.plan_workdir / "artifacts" / provider_id_sanitized
            # TODO: Not using exclude_pattern yet.
            provider.fetch_contents(guest, download_path)
        return outcome
