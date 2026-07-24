"""
Hints for users when facing installation-related issues.

Plugins, steps, and tmt code in general can register hints to be shown
to user when an important (or optional, but interesting) package is not
available.

Hints are shown when importing plugins fails, and rendered as part of
both their CLI help and HTML documentation.

Hints are registered, each having its own ID. A hint may take advantage
of ReST to format its content for better readability.

Hints should follow the rules of docstrings, i.e. provide a short summary
on the first line, followed by more details in the rest of the text.
"""

# NOTE (happz): in my plan, this module would be an unfinished, staging
# area for hints; eventually, I would like them to be managed under the
# umbrella of `tmt about` subcommand. `print_hint()` would still exist,
# but `tmt about` would be responsible for handling hints, therefore the
# code below may change, the concept should not. And hints would cover
# wider area, e.g. describing common errors and issues, not just when
# a package is missing. They would be coupled with exceptions tmt
# raises, providing more info on command-line and in HTML docs.

import functools
import re
import textwrap
from collections.abc import Iterator
from typing import Literal, Optional, cast, overload

import tmt.container
import tmt.log
import tmt.utils
import tmt.utils.rest
from tmt.log import Logger


@tmt.container.container
class Hint:
    #: Unique hint id
    id: str

    #: Detailed text with hint information
    text: str

    #: Regular expression patterns for searching the command line output
    cli_output_patterns: list[re.Pattern[str]] = tmt.container.simple_field(
        default_factory=list[re.Pattern[str]]
    )

    @functools.cached_property
    def summary(self) -> str:
        return self.text.splitlines()[0]

    @functools.cached_property
    def ref(self) -> str:
        return f'For more details, see ``tmt about {self.id}``.'

    @functools.cached_property
    def summary_ref(self) -> str:
        # TODO: once `tmt about` will be able to print hints, we shall
        # add ref as well.
        return self.summary

    def __init__(
        self, hint_id: str, text: str, cli_output_patterns: Optional[list[str]] = None
    ) -> None:
        """
        Initialize hint id, text and search patterns
        """

        self.id = hint_id
        self.text = textwrap.dedent(text).strip()
        self.cli_output_patterns = [re.compile(pattern) for pattern in (cli_output_patterns or [])]

    def _render(self, s: str, logger: Logger) -> str:
        if tmt.utils.rest.REST_RENDERING_ALLOWED:
            return tmt.utils.rest.render_rst(s, logger)

        return s

    def render_summary(self, logger: Logger) -> str:
        return self._render(self.summary, logger)

    def render_summary_ref(self, logger: Logger) -> str:
        return self._render(self.summary_ref, logger)

    def render(self, logger: Logger) -> str:
        return self._render(self.text, logger)

    def print(self, logger: Logger) -> None:
        """
        Print hint to the user
        """

        logger.info('hint', self.render(logger), color='blue')

    def search_cli_patterns(self, *outputs: Optional[str]) -> bool:
        """
        Check provided command line outputs for known error patterns
        """

        return any(
            any(pattern.search(output) for pattern in self.cli_output_patterns)
            for output in outputs
            if output is not None
        )


HINTS: dict[str, Hint] = {
    _hint_id: Hint(_hint_id, *_hint_info)
    for _hint_id, _hint_info in cast(
        dict[str, tuple[str, list[str]]],
        {
            'provision': (
                """
                You can use the ``local`` method to execute tests directly on your localhost.

                See ``tmt run provision --help`` for all available ``provision`` options.
                """,
                [],
            ),
            "report": (
                """
                You can use the ``display`` method to show test results on the terminal.

                See ``tmt run report --help`` for all available report options.
                """,
                [],
            ),
            'ansible-not-available': (
                """
                Make sure ``ansible-playbook`` is installed, it is required for preparing guests
                using Ansible playbooks.

                To quickly test ``ansible-playbook`` presence, you can try running
                ``ansible-playbook --help``.

                * Users who installed tmt from system repositories should install ``ansible-core``
                  package.
                * Users who installed tmt from PyPI should install ``tmt[ansible]`` extra.
                """,
                [r'ansible-playbook.*not found'],
            ),
            'guest-not-healthy': (
                """
                Guest was not in a healthy state.

                For some reason, the guest did not respond to any communication. This may be
                a result of a ``prepare`` or ``finish`` script, or a test. Among possible
                causes are kernel panic, stopped SSH daemon, new firewall rules blocking traffic,
                disabled user account tmt was expected to use, networking issues, or other
                infrastructure issues.
                """,
                [],
            ),
            'selinux-not-available': (
                """
                SELinux not detected on the guest.

                To support SELinux-based functionality, SELinux must be installed and enabled.
                To quickly test SELinux status, you can try running ``sestatus``.
                """,
                [],
            ),
            'systemd-not-available': (
                """
                Systemd not detected on the guest.

                The systemd init system must be running on the guest for this functionality.
                This is expected when using the ``container`` provisioner,
                where no init system is present.

                Use a provisioner that provisions VMs or bare-metal machines,
                such as ``virtual``, ``beaker``, etc.
                """,
                [],
            ),
            # TODO: once `minute` plugin provides its own hints, we can drop
            # this hint and move it to the plugin.
            'provision/minute': (
                """
                Make sure ``tmt-redhat-provision-minute`` package is installed, it is required for
                guests backed by 1minutetip OpenStack as provided by ``provision/minute`` plugin.
                The package is available from the internal COPR repository only.
                """,
                [],
            ),
        },
    ).items()
}


def register_hint(hint_id: str, hint: str) -> None:
    """
    Register a hint for users.

    :param hint_id: step name for step-specific hints,
        ``<step name>/<plugin name>`` for plugin-specific hints,
        or an arbitrary string.
    :param hint: a hint to register.
    """

    if hint_id in HINTS:
        raise tmt.utils.GeneralError(
            f"Registering hint '{hint_id}' collides with an already registered hint."
        )

    HINTS[hint_id] = Hint(hint_id, hint)


def get_hints(*ids: str, ignore_missing: bool = False) -> list[Hint]:
    """
    Find given hints.

    :param ids: ids of hints to retrieve.
    :param ignore_missing: if not set, non-existent hints will
        raise an exception. Otherwise, non-existent hints will
        be skipped.
    :returns: found hints.
    """

    if ignore_missing:

        def _get_optional_hints() -> Iterator[Hint]:
            for id_ in ids:
                hint = HINTS.get(id_)

                if hint is None:
                    continue

                yield hint

        return list(_get_optional_hints())

    def _render_mandatory_hints() -> Iterator[Hint]:
        for id_ in ids:
            hint = HINTS.get(id_)

            if hint is None:
                raise tmt.utils.GeneralError(f"Could not find hint '{id_}'.")

            yield hint

    return list(_render_mandatory_hints())


@overload
def get_hint(hint_id: str, ignore_missing: Literal[True]) -> Optional[Hint]:
    pass


@overload
def get_hint(hint_id: str, ignore_missing: Literal[False]) -> Hint:
    pass


def get_hint(hint_id: str, ignore_missing: bool = False) -> Optional[Hint]:
    """
    Return hint for the provided identifier

    :param hint_id: Hint identifier.
    :param ignore_missing: If not set, non-existent hint will raise an
        exception. Otherwise, non-existent hint will be skipped.
    :returns: Hint if found, None otherwise.
    """

    hints = get_hints(hint_id, ignore_missing=ignore_missing)

    return hints[0] if hints else None


def print_hints(*ids: str, ignore_missing: bool = False, logger: tmt.log.Logger) -> None:
    """
    Display given hints by printing them as info-level messages.

    :param ids: ids of hints to render.
    :param ignore_missing: if not set, non-existent hints will
        raise an exception.
    :param logger: to use for logging.
    """

    hints = get_hints(*ids, ignore_missing=ignore_missing)

    for hint in hints:
        hint.print(logger)


def hints_as_notes(*ids: str) -> list[str]:
    """
    Format hints as a list of :py:class:`Result` notes.

    :py:attr:`Hint.summary_ref` of each hint is added as a distinct
    note.
    """

    return [hint.summary_ref for hint in get_hints(*ids)]
