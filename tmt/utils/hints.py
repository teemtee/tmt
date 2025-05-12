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
import textwrap
from collections.abc import Iterator

import tmt.container
import tmt.log
import tmt.utils
import tmt.utils.rest
from tmt.log import Logger


@tmt.container.container
class Hint:
    id: str
    text: str

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

    def __init__(self, hint_id: str, text: str) -> None:
        self.id = hint_id
        self.text = textwrap.dedent(text).strip()

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


HINTS: dict[str, Hint] = {
    _hint_id: Hint(_hint_id, _hint)
    for _hint_id, _hint in {
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
    }.items()
}


def register_hint(id_: str, hint: str) -> None:
    """
    Register a hint for users.

    :param id_: step name for step-specific hints,
        ``<step name>/<plugin name>`` for plugin-specific hints,
        or an arbitrary string.
    :param hint: a hint to register.
    """

    if id_ in HINTS:
        raise tmt.utils.GeneralError(
            f"Registering hint '{id_}' collides with an already registered hint."
        )

    HINTS[id_] = Hint(id_, hint)


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
        logger.info('hint', hint.render(logger), color='blue')
