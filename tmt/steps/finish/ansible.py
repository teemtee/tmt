import tmt.steps
import tmt.steps.finish
import tmt.steps.prepare.ansible
from tmt.steps.prepare.ansible import PrepareAnsible


@tmt.steps.provides_method('ansible')
class FinishAnsible(
    tmt.steps.finish.FinishPlugin[tmt.steps.finish.FinishStepData], PrepareAnsible
):
    """
    Perform finishing tasks using ansible.

    One or more playbooks can be provided as a list under the ``playbook``
    attribute.  Each of them will be applied using ``ansible-playbook`` in
    the given order. The path must be relative to the metadata tree root.

    Remote playbooks can be referenced as well as the local ones,
    and both kinds can be used at the same time.

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
              - playbooks/common.yml
              - playbooks/os/rhel9.yml
              - https://foo.bar/rhel9-final-touches.yml

    The playbook path should be relative to the metadata tree root. Use
    the :ref:`/spec/core/order` attribute to select in which order
    finishing tasks should happen if there are multiple configs. Default
    order is ``50``.
    """

    # We are reusing "prepare" step for "finish",
    # and they both have different expectations
    _data_class = tmt.steps.prepare.ansible.PrepareAnsibleData

    # FIXME: ignore[assignment]: https://github.com/teemtee/tmt/issues/1540
    # Also, assigning class methods seems to cause trouble to mypy
    # See https://github.com/python/mypy/issues/6700
    base_command = tmt.steps.finish.FinishPlugin.base_command  # type: ignore[assignment]

    # `FinishPlugin` plugin would win the inheritance battle and provide
    # its no-op `go()`. Force the one from `PrepareAnsible`.
    go = PrepareAnsible.go
