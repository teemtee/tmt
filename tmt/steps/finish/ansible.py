import tmt.steps
import tmt.steps.finish
import tmt.steps.prepare.ansible
from tmt.steps.prepare.ansible import PrepareAnsible


@tmt.steps.provides_method('ansible')
class FinishAnsible(
        tmt.steps.finish.FinishPlugin[tmt.steps.finish.FinishStepData], PrepareAnsible):
    """
    Perform finishing tasks using ansible

    Single playbook config:

    .. code-block:: yaml

        finish:
            how: ansible
            playbook: ansible/packages.yml

    Multiple playbooks config:

    .. code-block:: yaml

        finish:
            how: ansible
            playbook:
              - playbook/one.yml
              - playbook/two.yml
              - playbook/three.yml

    The playbook path should be relative to the metadata tree root.
    Use 'order' attribute to select in which order finishing tasks
    should happen if there are multiple configs. Default order is '50'.
    """

    # We are re-using "prepare" step for "finish",
    # and they both have different expectations
    _data_class = tmt.steps.prepare.ansible.PrepareAnsibleData

    # FIXME: ignore[assignment]: https://github.com/teemtee/tmt/issues/1540
    # Also, assigning class methods seems to cause trouble to mypy
    # See https://github.com/python/mypy/issues/6700
    base_command = tmt.steps.finish.FinishPlugin.base_command  # type: ignore[assignment]

    # `FinishPlugin` plugin would win the inheritance battle and provide
    # its no-op `go()`. Force the one from `PrepareAnsible`.
    go = PrepareAnsible.go
