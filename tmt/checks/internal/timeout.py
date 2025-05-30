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
class InternalTimeoutCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class InternalTimeout(CheckPlugin[InternalTimeoutCheck]):
    _check_class = InternalTimeoutCheck

    @classmethod
    def before_test(
        cls,
        *,
        check: 'InternalTimeoutCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        return []

    @classmethod
    def after_test(
        cls,
        *,
        check: 'InternalTimeoutCheck',
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
