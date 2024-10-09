import enum


class CheckEvent(enum.Enum):
    """ Events in test runtime when a check can be executed """

    BEFORE_TEST = 'before-test'
    AFTER_TEST = 'after-test'

    @classmethod
    def from_spec(cls, spec: str) -> 'CheckEvent':
        try:
            return CheckEvent(spec)
        except ValueError:
            raise ValueError(f"Invalid test check event '{spec}'.")


class CheckResultInterpret(enum.Enum):
    INFO = 'info'
    RESPECT = 'respect'
    XFAIL = 'xfail'

    @classmethod
    def from_spec(cls, spec: str) -> 'CheckResultInterpret':
        try:
            return CheckResultInterpret(spec)
        except ValueError:
            raise ValueError(f"Invalid check result interpretation '{spec}'.")
