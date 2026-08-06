"""
Unsafe behavior ("UB") and "feeling safe" handling.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, ClassVar, NoReturn, Optional

import packaging.version
from fmf.utils import listed  # type: ignore[reportUnknownVariableType,unused-ignore]

from tmt.container import container

if TYPE_CHECKING:
    from tmt.log import Logger


@container(frozen=True)
class UnsafeBehavior:
    """
    Describes behavior that is not allowed when not "feeling safe".
    """

    #: Name of the unsafe behavior to use in options.
    name: str

    #: Human-understandable label to use in logging and error messages.
    label: str

    #: If set, it is the tmt version since which the behavior is
    #: not allowed without the "feeling safe" mode. Older tmt will allow
    #: the behavior, emitting only a warning about the future
    #: versions.
    locked_since: Optional[str] = None

    #: All unsafe behavior recognized by tmt.
    KNOWN_UB: ClassVar[set['UnsafeBehavior']] = set()

    def __post_init__(self) -> None:
        UnsafeBehavior.KNOWN_UB.add(self)

    @property
    def is_allowed(self) -> bool:
        """
        Whether the behavior is allowed given the "feeling safe" setting.
        """

        if _NONE_ in ALLOWED_BEHAVIORS:
            return False

        if _ALL_ in ALLOWED_BEHAVIORS:
            return True

        return self in ALLOWED_BEHAVIORS

    def _not_allowed(self) -> NoReturn:
        from tmt.utils import GeneralError

        raise GeneralError(
            f"{self.label.capitalize()} is allowed only with the '--feeling-safe' option."
        )

    def assert_is_allowed(self, logger: 'Logger') -> None:
        """
        Test whether the behavior is allowed, and take action when not.

        :param logger: logger to use for logging.
        :raises tmt.utils.GeneralError: when the current "feeling safe"
            setting does not allow this behavior.
        """

        if self.is_allowed:
            return

        if self.locked_since is not None:
            import tmt

            if packaging.version.Version(tmt.__version__) < packaging.version.Version(
                self.locked_since
            ):
                logger.warning(
                    f"Starting with tmt {self.locked_since}, {self.label}"
                    " will require '--feeling-safe' option."
                )

                return

        self._not_allowed()


#: Represents all possible unsafe behavior.
_ALL_ = UnsafeBehavior(name='all', label='all unsafe behavior')

#: Represents no unsafe behavior.
_NONE_ = UnsafeBehavior(name='none', label='no unsafe behavior')

UB_CONDITION_CLI_OPTION = UnsafeBehavior(
    name='cli.condition', label="'--condition' command-line option"
)

UB_UNSAFE_SSH_OPTIONS = UnsafeBehavior(
    name='provision.unsafe-ssh-options', label='unsafe SSH option'
)

# TODO: move to `provision/connect`
#: When enabled, allows keys defining custom reboot commands the plugin
#: runs on the runner.
UB_REBOOT_KEYS = UnsafeBehavior(
    name='provision/connect.reboot-commands',
    label='custom soft, systemd soft, and hard reboot commands',
)

# TODO: move to `provision/mock`
#: When enabled, allows usage of the :ref:`/plugins/provision/mock`
#: plugin.
UB_PROVISION_MOCK_PLUGIN = UnsafeBehavior(
    name='provision/mock', label='mock provisioning plugin', locked_since='1.58'
)

# TODO: move to `provision/local`
#: When enabled, allows usage of the :ref:`/plugins/provision/local`
#: plugin.
UB_PROVISION_LOCAL_PLUGIN = UnsafeBehavior(
    name='provision/local', label="'local' provisioning plugin", locked_since="1.38"
)

#: Behavior currently enabled.
ALLOWED_BEHAVIORS: set[UnsafeBehavior] = set()


def name_to_unsafe_behavior(*names: str) -> Iterator[UnsafeBehavior]:
    known_ub_map = {ub.name: ub for ub in UnsafeBehavior.KNOWN_UB}
    requested_ub_names = set(names)

    unknown_but_requested_names = requested_ub_names.difference(known_ub_map.keys())

    if unknown_but_requested_names:
        from tmt.utils import GeneralError

        raise GeneralError(f"Unknown unsafe behavior {listed(unknown_but_requested_names)}.")

    for name in requested_ub_names:
        yield known_ub_map[name]


def allow_unsafe_behavior(*ubs: str) -> None:
    """
    Allow the given unsafe behaviors.

    All other unsafe behaviors would not be allowed: the
    list of allowed behaviors is emptied, and then populated with
    the provided set.
    """

    global ALLOWED_BEHAVIORS

    ALLOWED_BEHAVIORS.clear()

    for ub in name_to_unsafe_behavior(*ubs):
        ALLOWED_BEHAVIORS.add(ub)


def is_allowed(*names: str) -> bool:
    """
    Check whether the given unsafe behaviors are allowed.
    """

    global ALLOWED_BEHAVIORS

    known_ub_map = {ub.name: ub for ub in UnsafeBehavior.KNOWN_UB}

    try:
        return all(known_ub_map[name].is_allowed for name in names)

    except KeyError as exc:
        from tmt.utils import GeneralError

        raise GeneralError(f"Unknown unsafe behavior {listed([exc.args[0]])}.") from exc


def log_feeling_safe(logger: 'Logger') -> None:
    """
    Log how safe is the user feeling.
    """

    if not ALLOWED_BEHAVIORS:
        logger.debug(f'User is not feeling safe: {_NONE_.label} allowed.')

    elif _NONE_ in ALLOWED_BEHAVIORS:
        logger.warning(f'User is not feeling safe: {_NONE_.label} allowed.')

    elif _ALL_ in ALLOWED_BEHAVIORS:
        logger.warning(f'User is feeling safe: {_ALL_.label} allowed.')

    else:
        logger.warning(
            'User is feeling safe:'
            f' {listed(behavior.label for behavior in ALLOWED_BEHAVIORS)} allowed.'
        )
