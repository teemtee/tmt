from typing import Optional

import tmt.log
import tmt.utils
from tmt.checks import CheckPlugin, provides_check
from tmt.checks.internal import InternalCheck
from tmt.container import container
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.execute import TestInvocation

CHECK_NAME = 'internal/guest'


@container
class GuestCheck(InternalCheck):
    how: str = CHECK_NAME


@provides_check(CHECK_NAME)
class GuestFailures(CheckPlugin[GuestCheck]):
    """
    Check for guest errors during test execution.

    This check fails when guest related errors occur during test execution,
    such as reboot or reconnect timeouts.

    .. note::

        This is an :ref:`internal check </plugins/test-checks/internal>`,
        and it cannot be enabled or disabled by test metadata.

    .. versionadded:: 1.53
    """

    _check_class = GuestCheck

    @classmethod
    def after_test(
        cls,
        *,
        check: 'GuestCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if any(isinstance(exc, tmt.utils.RebootTimeoutError) for exc in invocation.exceptions):
            return [
                CheckResult(
                    name=CHECK_NAME,
                    result=ResultOutcome.FAIL,
                    note=['Test failed due to guest reboot timeout.'],
                )
            ]

        if any(isinstance(exc, tmt.utils.ReconnectTimeoutError) for exc in invocation.exceptions):
            return [
                CheckResult(
                    name=CHECK_NAME,
                    result=ResultOutcome.FAIL,
                    note=['Test failed due to guest reconnect timeout.'],
                )
            ]

        return []
