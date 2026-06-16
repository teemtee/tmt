from typing import Optional

import tmt.log
from tmt.container import container
from tmt.steps.context import StepContext
from tmt.utils.environment import Environment, OpenEnvVarValue


@container
class RestraintContext(StepContext):
    """
    Provides restraint-related context for execution.
    """

    #: Phase owning this context.
    # phase: tmt.steps.Phase

    enabled: bool

    #: Used for logging.
    logger: tmt.log.Logger

    taskname: Optional[str] = None

    @property
    def intrinsic_environment(self) -> Environment:
        environment = Environment()

        environment["TMT_RESTRAINT_COMPATIBLE"] = OpenEnvVarValue(str(int(self.enabled)))

        if self.enabled and self.taskname:
            environment["RSTRNT_TASKNAME"] = OpenEnvVarValue(self.taskname)

        return environment
