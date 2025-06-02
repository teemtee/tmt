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

import fnmatch
import functools
import re
import textwrap
from collections.abc import Sequence
from typing import Optional, Union

import tmt.container
import tmt.log
import tmt.utils
import tmt.utils.rest
from tmt.log import Logger


@tmt.container.container
class Hint:
    """A hint for users with formatted text and rendering capabilities."""

    id: str
    text: str

    def __init__(self, hint_id: str, text: str) -> None:
        """
        Initialize a hint.

        :param hint_id: unique identifier for the hint
        :param text: hint content, may contain ReST formatting
        """
        self.id = hint_id
        self.text = textwrap.dedent(text).strip()

    @functools.cached_property
    def summary(self) -> str:
        """Get the first line of the hint as a summary."""
        return self.text.splitlines()[0]

    @functools.cached_property
    def ref(self) -> str:
        """Get a reference to the full hint via tmt about command."""
        return f'For more details, see ``tmt about {self.id}``.'

    @functools.cached_property
    def summary_ref(self) -> str:
        """Get the summary with reference (currently just summary)."""
        # TODO: once `tmt about` will be able to print hints, we shall
        # add ref as well.
        return self.summary

    def _render(self, text: str, logger: Logger) -> str:
        """Render text with ReST if available."""
        if tmt.utils.rest.REST_RENDERING_ALLOWED:
            return tmt.utils.rest.render_rst(text, logger)
        return text

    def render_summary(self, logger: Logger) -> str:
        """Render the hint summary."""
        return self._render(self.summary, logger)

    def render_summary_ref(self, logger: Logger) -> str:
        """Render the hint summary with reference."""
        return self._render(self.summary_ref, logger)

    def render(self, logger: Logger) -> str:
        """Render the full hint text."""
        return self._render(self.text, logger)


# Pre-defined hints for common scenarios
_PREDEFINED_HINTS = {
    'provision': """
        You can use the ``local`` method to execute tests directly on your localhost.

        See ``tmt run provision --help`` for all available ``provision`` options.
        """,
    "report": """
        You can use the ``display`` method to show test results on the terminal.

        See ``tmt run report --help`` for all available report options.
        """,
    'ansible-not-available': """
        Make sure ``ansible-playbook`` is installed, it is required for preparing guests using
        Ansible playbooks.

        To quickly test ``ansible-playbook`` presence, you can try running
        ``ansible-playbook --help``.

        * Users who installed tmt from system repositories should install ``ansible-core``
          package.
        * Users who installed tmt from PyPI should install ``tmt[ansible]`` extra.
        """,
    # TODO: once `minute` plugin provides its own hints, we can drop
    # this hint and move it to the plugin.
    'provision/minute': """
        Make sure ``tmt-redhat-provision-minute`` package is installed, it is required for
        guests backed by 1minutetip OpenStack as provided by ``provision/minute`` plugin. The
        package is available from the internal COPR repository only.
        """,
}

# Global registry of all hints
HINTS: dict[str, Hint] = {
    hint_id: Hint(hint_id, hint_text) for hint_id, hint_text in _PREDEFINED_HINTS.items()
}


def register_hint(hint_id: str, hint_text: str) -> None:
    """
    Register a hint for users.

    :param hint_id: step name for step-specific hints,
        ``<step name>/<plugin name>`` for plugin-specific hints,
        or an arbitrary string.
    :param hint_text: a hint to register.
    :raises GeneralError: if hint ID already exists
    """
    if hint_id in HINTS:
        raise tmt.utils.GeneralError(
            f"Registering hint '{hint_id}' collides with an already registered hint."
        )

    HINTS[hint_id] = Hint(hint_id, hint_text)


def get_hints(*hint_ids: str, ignore_missing: bool = False) -> list[Hint]:
    """
    Find given hints.

    :param hint_ids: IDs of hints to retrieve.
    :param ignore_missing: if False, non-existent hints will raise an exception.
        If True, non-existent hints will be skipped.
    :returns: found hints.
    :raises GeneralError: if ignore_missing is False and a hint is not found
    """
    found_hints: list[Hint] = []

    for hint_id in hint_ids:
        hint = HINTS.get(hint_id)

        if hint is None:
            if not ignore_missing:
                raise tmt.utils.GeneralError(f"Could not find hint '{hint_id}'.")
            continue

        found_hints.append(hint)

    return found_hints


def print_hints(*hint_ids: str, ignore_missing: bool = False, logger: tmt.log.Logger) -> None:
    """
    Display given hints by printing them as info-level messages.

    :param hint_ids: IDs of hints to render.
    :param ignore_missing: if False, non-existent hints will raise an exception.
    :param logger: logger to use for output.
    """
    hints = get_hints(*hint_ids, ignore_missing=ignore_missing)

    for hint in hints:
        logger.info('hint', hint.render(logger), color='blue')


def check_for_message(
    patterns: Sequence[re.Pattern[str]], outputs: Sequence[Optional[str]]
) -> bool:
    """
    Check one or more output strings for expected error message using regex patterns.

    :param patterns: list of compiled regular expressions to search for
    :param outputs: command output strings to search
    :returns: True if any pattern matches any of the provided outputs
    """
    return any(
        pattern.search(output) for output in outputs if output is not None for pattern in patterns
    )


def check_for_glob_message(patterns: Sequence[str], outputs: Sequence[Optional[str]]) -> bool:
    """
    Check one or more output strings for expected error message using glob patterns.

    :param patterns: list of glob patterns to search for
    :param outputs: command output strings to search
    :returns: True if any pattern matches any of the provided outputs
    """
    return any(
        fnmatch.fnmatch(output, pattern)
        for output in outputs
        if output is not None
        for pattern in patterns
    )


def check_for_pattern_message(
    patterns: Sequence[Union[str, re.Pattern[str]]],
    outputs: Sequence[Optional[str]],
    use_glob: bool = False,
) -> bool:
    """
    Check one or more output strings for expected error message using either regex or glob patterns.

    :param patterns: list of patterns (strings or compiled regex) to search for
    :param outputs: command output strings to search
    :param use_glob: if True, treat string patterns as glob patterns;
        if False, treat them as regex patterns
    :returns: True if any pattern matches any of the provided outputs
    """  # noqa: E501

    def _pattern_matches(pattern: Union[str, re.Pattern[str]], output: str) -> bool:
        if isinstance(pattern, re.Pattern):
            # Always use regex for compiled patterns
            return pattern.search(output) is not None
        # Use glob matching for string patterns when requested
        return fnmatch.fnmatch(output, pattern)
        # Use regex matching for string patterns by default
        return re.search(pattern, output) is not None

    return any(
        _pattern_matches(pattern, output)
        for output in outputs
        if output is not None
        for pattern in patterns
    )
