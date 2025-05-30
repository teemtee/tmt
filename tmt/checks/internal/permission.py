from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes

CHECK_NAME = 'internal/permission'


@container
class InternalPermissionCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class InternalPermission(CheckPlugin[InternalPermissionCheck]):
    _check_class = InternalPermissionCheck

    @classmethod
    def before_test(
        cls,
        *,
        check: 'InternalPermissionCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        return []

    @classmethod
    def after_test(
        cls,
        *,
        check: 'InternalPermissionCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if invocation.return_code == ProcessExitCodes.PERMISSION_DENIED:
            return [
                CheckResult(
                    name=CHECK_NAME,
                    result=ResultOutcome.FAIL,
                    note=['Test failed due to denied permissions'],
                )
            ]

        return []
