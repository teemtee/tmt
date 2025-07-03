from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.abort import AbortStep
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

    .. note::

        This is an :ref:`internal check </plugins/test-checks/internal>`,
        and it cannot be enabled or disabled by test metadata.

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
        if (
            invocation.abort.requested and invocation.return_code != ProcessExitCodes.SUCCESS
        ) or any(isinstance(exc, AbortStep) for exc in invocation.exceptions):
            return [CheckResult(name=CHECK_NAME, result=ResultOutcome.FAIL, note=['Test aborted'])]

        return []
