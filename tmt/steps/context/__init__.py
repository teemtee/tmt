import abc
from typing import TYPE_CHECKING, Optional

from tmt.container import container
from tmt.utils.environment import HasIntrinsicEnvironment

if TYPE_CHECKING:
    from tmt.steps.context.reboot import RebootContext
    from tmt.steps.context.restart import RestartContext


def is_guest_healthy(
    reboot: Optional['RebootContext'] = None, restart: Optional['RestartContext'] = None
) -> bool:
    if reboot and reboot.hard_requested:
        return False

    if restart and restart.requested:
        return False

    return True


@container
class StepContext(HasIntrinsicEnvironment, abc.ABC):
    pass
