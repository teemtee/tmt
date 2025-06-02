from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes

CHECK_NAME = 'internal/abort'


@container
class AbortCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class Abort(CheckPlugin[AbortCheck]):
    """
    Check for test aborts during execution.

    This check fails when tests are aborted before completion.

    .. versionadded:: 1.50
    """

    _check_class = AbortCheck

    @classmethod
    def after_test(
        cls,
        *,
        check: 'AbortCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if invocation.abort_requested and invocation.return_code != ProcessExitCodes.SUCCESS:
            return [CheckResult(name=CHECK_NAME, result=ResultOutcome.FAIL, note=['Test aborted'])]

        return []
