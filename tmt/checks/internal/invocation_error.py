from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes

CHECK_NAME = 'internal/invocation-error'


@container
class InvocationErrorCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class InvocationError(CheckPlugin[InvocationErrorCheck]):
    _check_class = InvocationErrorCheck

    @classmethod
    def before_test(
        cls,
        *,
        check: 'InvocationErrorCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        return []

    @classmethod
    def after_test(
        cls,
        *,
        check: 'InvocationErrorCheck',
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
