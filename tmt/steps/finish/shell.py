import tmt
import tmt.steps
import tmt.steps.finish
from tmt.steps.prepare.shell import PrepareShell


@tmt.steps.provides_method('shell')
class FinishShell(tmt.steps.finish.FinishPlugin[tmt.steps.finish.FinishStepData], PrepareShell):
    """
    Perform finishing tasks using shell (bash) scripts.

    Execute arbitrary shell commands to finish the testing.
    Default shell options are applied to the script, see the
    :ref:`/spec/tests/test` key specification for more
    details.

    Example config:

    .. code-block:: yaml

        finish:
            how: shell
            script:
              - upload-logs.sh || true
              - rm -rf /tmp/temporary-files

    Scripts can also be fetched from a remote git repository.
    Specify the ``url`` for the repository and optionally ``ref``
    to checkout a specific branch, tag or commit.
    The ``script`` paths will then be treated as relative to the
    repository root.

    .. code-block:: yaml

        finish:
            how: shell
            url: https://github.com/teemtee/tmt.git
            ref: my_branch
            script:
              - tmt/steps/finish/script.sh

    Use the :ref:`/spec/core/order` attribute to select in which order
    finishing tasks should happen if there are multiple configs. Default
    order is ``50``.
    """

    # We are reusing "prepare" step for "finish",
    # and they both have different expectations
    _data_class = tmt.steps.prepare.shell.PrepareShellData

    # `FinishPlugin` plugin would win the inheritance battle and provide
    # its no-op `go()`. Force the one from `PrepareShell`.
    go = PrepareShell.go