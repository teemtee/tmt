import tmt.log
from tmt.checks import Check, _RawCheck
from tmt.container import container


@container
class InternalCheck(Check):
    """
    Represents an internal check for various test execution issues.
    """

    @classmethod
    def create_internal(cls, logger: tmt.log.Logger) -> Check:
        return cls.from_spec(_RawCheck(how=cls.how, enabled=True, result='respect'), logger)
