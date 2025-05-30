import tmt.log
from tmt.checks import Check, _RawCheck
from tmt.container import container


@container
class InternalCheck(Check):
    @classmethod
    def create_default(cls, logger: tmt.log.Logger) -> Check:
        return cls.from_spec(_RawCheck(how=cls.how, enabled=True, result='respect'), logger)
