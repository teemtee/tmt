from typing import Optional

import tmt.log
import tmt.utils
import tmt.utils.signals
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes

CHECK_NAME = 'internal/interrupt'


@container
class InterruptCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class Interrupt(CheckPlugin[InterruptCheck]):
    """
    Check for signal interruptions during test execution.

    This check fails when tests are interrupted by SIGINT or SIGTERM signals.

    .. note::

        This is an :ref:`internal check </plugins/test-checks/internal>`,
        and it cannot be enabled or disabled by test metadata.

    .. versionadded:: 1.50
    """

    _check_class = InterruptCheck

    @classmethod
    def after_test(
        cls,
        *,
        check: 'InterruptCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if invocation.return_code in (ProcessExitCodes.SIGINT, ProcessExitCodes.SIGTERM) or any(
            isinstance(exc, tmt.utils.signals.Interrupted) for exc in invocation.exceptions
        ):
            return [
                CheckResult(
                    name=CHECK_NAME, result=ResultOutcome.FAIL, note=['Test interrupted by signal']
                )
            ]

        return []
