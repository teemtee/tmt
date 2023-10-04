import tmt.steps
import tmt.steps.finish
import tmt.steps.prepare.reboot
from tmt.steps.prepare.reboot import PrepareReboot


@tmt.steps.provides_method('reboot')
class FinishReboot(tmt.steps.finish.FinishPlugin, PrepareReboot):
    """
    Reboot system via provided script
    Example config:
    finish:
        how: reboot
        script: ./reboot-script
    """

    # We are re-using "prepare" step for "finish",
    # and they both have different expectations
    _data_class = tmt.steps.prepare.reboot.PrepareRebootData  # type: ignore[assignment]

    # Assigning class methods seems to cause trouble to mypy
    # See also: https://github.com/python/mypy/issues/6700
    base_command = tmt.steps.finish.FinishPlugin.base_command  # type: ignore[assignment]
