from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes

CHECK_NAME = 'internal/timeout'


@container
class TimeoutCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class Timeout(CheckPlugin[TimeoutCheck]):
    """
    Check for test timeouts during execution.

    This check fails when tests exceed their maximum allowed duration.

    .. note::

        This is an :ref:`internal check </plugins/test-checks/internal>`,
        and it cannot be enabled or disabled by test metadata.

    .. versionadded:: 1.50
    """

    _check_class = TimeoutCheck

    @classmethod
    def after_test(
        cls,
        *,
        check: 'TimeoutCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if invocation.return_code == ProcessExitCodes.TIMEOUT:
            return [
                CheckResult(
                    name=CHECK_NAME,
                    result=ResultOutcome.FAIL,
                    note=[f'Test exceeded maximum duration of {invocation.test.duration}'],
                )
            ]

        return []
