"""
Unsafe behavior and "feeling safe" handling.
"""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, NoReturn, Optional, cast

import fmf.utils
import packaging.version

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

        return self in ALLOWED_BEHAVIOR or _ALL_ in ALLOWED_BEHAVIOR

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

# TODO: move to `provision/connect`
#: When enabled, allows keys defining custom reboot commands the plugin
#: runs on the runner.
REBOOT_KEYS_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='prepare/connect.reboot-commands',
    label='custom soft, systemd soft, and hard reboot commands',
)

# TODO: move to `provision/mock`
#: When enabled, allows usage of the :ref:`/plugins/provision/mock`
#: plugin.
PROVISION_MOCK_PLUGIN_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='provision/mock', label='mock provisioning plugin', locked_since='1.58'
)

# TODO: move to `provision/login`
#: When enabled, allows usage of the :ref:`/plugins/provision/mock`
#: plugin.
PROVISION_LOCAL_PLUGIN_UNSAFE_BEHAVIOR = UnsafeBehavior(
    name='provision/local', label="'local' provisioning plugin", locked_since="1.38"
)


#: All unsafe behavior recognized by tmt.
KNOWN_UNSAFE_BEHAVIOR: set[UnsafeBehavior] = {
    _ALL_,
    REBOOT_KEYS_UNSAFE_BEHAVIOR,
    PROVISION_MOCK_PLUGIN_UNSAFE_BEHAVIOR,
    PROVISION_LOCAL_PLUGIN_UNSAFE_BEHAVIOR,
}

#: Behavior currently enabled.
ALLOWED_BEHAVIOR: set[UnsafeBehavior] = set()


def functionalities_to_names() -> Iterator[str]:
    for functionality in KNOWN_UNSAFE_BEHAVIOR:
        yield functionality.name


def names_to_behavior(names: Sequence[str]) -> Iterator[UnsafeBehavior]:
    behavior_map = {behavior.name: behavior for behavior in KNOWN_UNSAFE_BEHAVIOR}

    for name in names:
        behavior = behavior_map.get(name)

        if behavior is None:
            from tmt.utils import GeneralError

            raise GeneralError(f"Unknown unsafe behavior '{name}'.")

        yield behavior


def format_allowed_behavior() -> str:
    if _ALL_ in ALLOWED_BEHAVIOR:
        return _ALL_.label

    return cast(str, fmf.utils.listed(behavior.label for behavior in ALLOWED_BEHAVIOR))


def allow_behavior(names: Sequence[str]) -> None:
    """
    Allow the given behavior.

    All other unsafe behavior would not be allowed: the
    list of allowed behavior is emptied, and then populated with
    the requested behavior.
    """

    global ALLOWED_BEHAVIOR

    ALLOWED_BEHAVIOR.clear()

    for behavior in names_to_behavior(names):
        ALLOWED_BEHAVIOR.add(behavior)
