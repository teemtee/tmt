from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes

CHECK_NAME = 'internal/interrupt'


@container
class InternalInterruptCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class InternalInterrupt(CheckPlugin[InternalInterruptCheck]):
    _check_class = InternalInterruptCheck

    @classmethod
    def before_test(
        cls,
        *,
        check: 'InternalInterruptCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        return []

    @classmethod
    def after_test(
        cls,
        *,
        check: 'InternalInterruptCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if invocation.return_code in (ProcessExitCodes.SIGINT, ProcessExitCodes.SIGTERM):
            return [
                CheckResult(
                    name=CHECK_NAME, result=ResultOutcome.FAIL, note=['Test interrupted by signal']
                )
            ]

        return []
