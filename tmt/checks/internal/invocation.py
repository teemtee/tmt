from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes

CHECK_NAME = 'internal/invocation'


@container
class InvocationCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class Invocation(CheckPlugin[InvocationCheck]):
    """
    Check for uncategorized invocation errors during test execution.

    This check fails when tests encounter errors that are not covered
    by more specific checks.

    .. versionadded:: 1.50
    """

    _check_class = InvocationCheck

    @classmethod
    def after_test(
        cls,
        *,
        check: 'InvocationCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if ProcessExitCodes.is_pidfile(invocation.return_code):
            return [
                CheckResult(
                    name=CHECK_NAME,
                    result=ResultOutcome.FAIL,
                    note=['Test failed due to pidfile locking'],
                )
            ]

        return []
