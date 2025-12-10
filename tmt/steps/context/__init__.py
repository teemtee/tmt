from typing import TYPE_CHECKING, Optional

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
