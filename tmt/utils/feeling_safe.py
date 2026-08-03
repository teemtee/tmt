"""
Unsafe behavior and "feeling safe" handling.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING, NoReturn, Optional

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

CONDITION_CLI_OPTION_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='cli.condition', label="'--condition' command-line option"
)

UNSAFE_SSH_OPTIONS_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='provision.unsafe-ssh-options', label='unsafe SSH option'
)

# TODO: move to `provision/connect`
#: When enabled, allows keys defining custom reboot commands the plugin
#: runs on the runner.
REBOOT_KEYS_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='provision/connect.reboot-commands',
    label='custom soft, systemd soft, and hard reboot commands',
)

# TODO: move to `provision/mock`
#: When enabled, allows usage of the :ref:`/plugins/provision/mock`
#: plugin.
PROVISION_MOCK_PLUGIN_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='provision/mock', label='mock provisioning plugin', locked_since='1.58'
)

# TODO: move to `provision/local`
#: When enabled, allows usage of the :ref:`/plugins/provision/local`
#: plugin.
PROVISION_LOCAL_PLUGIN_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='provision/local', label="'local' provisioning plugin", locked_since="1.38"
)


#: All unsafe behavior recognized by tmt.
KNOWN_UNSAFE_BEHAVIORS: set[UnsafeBehavior] = {
    _ALL_,
    _NONE_,
    CONDITION_CLI_OPTION_UNSAFE_BEHAVIOR,
    UNSAFE_SSH_OPTIONS_UNSAFE_BEHAVIOR,
    REBOOT_KEYS_UNSAFE_BEHAVIOR,
    PROVISION_MOCK_PLUGIN_UNSAFE_BEHAVIOR,
    PROVISION_LOCAL_PLUGIN_UNSAFE_BEHAVIOR,
}

#: Behavior currently enabled.
ALLOWED_BEHAVIORS: set[UnsafeBehavior] = set()


def names_to_behaviors(*names: str) -> Iterator[UnsafeBehavior]:
    known_behavior_map = {behavior.name: behavior for behavior in KNOWN_UNSAFE_BEHAVIORS}
    requsted_behavior_names = set(names)

    unknown_but_requested_names = requsted_behavior_names.difference(known_behavior_map.keys())

    if unknown_but_requested_names:
        from tmt.utils import GeneralError

        raise GeneralError(f"Unknown unsafe behavior {listed(unknown_but_requested_names)}.")

    for name in requsted_behavior_names:
        yield known_behavior_map[name]


def allow_behaviors(*behaviors: str) -> None:
    """
    Allow the given behaviors.

    All other unsafe behaviors would not be allowed: the
    list of allowed behaviors is emptied, and then populated with
    the provided set.
    """

    global ALLOWED_BEHAVIORS

    ALLOWED_BEHAVIORS.clear()

    for behavior in names_to_behaviors(*behaviors):
        ALLOWED_BEHAVIORS.add(behavior)


def is_allowed(*names: str) -> bool:
    """
    Check whether the given behaviors are allowed.
    """

    global ALLOWED_BEHAVIORS

    known_behavior_map = {behavior.name: behavior for behavior in KNOWN_UNSAFE_BEHAVIORS}

    try:
        return all(known_behavior_map[name].is_allowed for name in names)

    except KeyError as exc:
        from tmt.utils import GeneralError

        raise GeneralError(f"Unknown unsafe behavior {listed([exc.args[0]])}.") from exc


def is_feeling_safe() -> tuple[bool, bool, str]:
    """
    Find out whether tmt runs in a "feeling safe" mode, and how much.

    Besides the obvious statement and helpful message for logging, it
    is also determined how strongly user felt about this mode: not
    feeling safe and providing ``--feeling-safe=none`` option is stronger
    than just running tmt and relying on unsafe behavior being disabled
    by default.

    :returns: a tuple of 3 items: whether tmt runs in the "feeling safe"
        mode, how strong is this decision, and user-friendly message
        for logging.
    """

    if not ALLOWED_BEHAVIORS:
        return (False, False, f'User is not feeling safe: {_NONE_.label} allowed')

    if _NONE_ in ALLOWED_BEHAVIORS:
        return (False, True, f'User is not feeling safe: {_NONE_.label} allowed')

    if _ALL_ in ALLOWED_BEHAVIORS:
        return (True, True, f'User is feeling safe: {_ALL_.label} allowed')

    return (
        True,
        True,
        'User is feeling safe:'
        f' {listed(behavior.label for behavior in ALLOWED_BEHAVIORS)} allowed',
    )
