from typing import Optional

import tmt.log
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation
from tmt.utils import ProcessExitCodes
from tmt.utils.environment import Environment

CHECK_NAME = 'internal/permission'


@container
class PermissionCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class Permission(CheckPlugin[PermissionCheck]):
    """
    Check for permission issues during execution.

    This check fails when tests encounter permission-related errors.

    .. note::

        This is an :ref:`internal check </plugins/test-checks/internal>`,
        and it cannot be enabled or disabled by test metadata.

    .. versionadded:: 1.50
    """

    _check_class = PermissionCheck

    @classmethod
    def after_test(
        cls,
        *,
        check: 'PermissionCheck',
        invocation: 'TestInvocation',
        environment: Optional[Environment] = None,
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
