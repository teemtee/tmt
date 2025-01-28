import tmt.steps
import tmt.steps.finish
import tmt.steps.prepare.ansible
from tmt.steps.prepare.ansible import PrepareAnsible


@tmt.steps.provides_method('ansible')
class FinishAnsible(
        tmt.steps.finish.FinishPlugin[tmt.steps.finish.FinishStepData], PrepareAnsible):
    """
    Perform finishing tasks using ansible

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
