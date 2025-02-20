"""
Hints for users when facing installation-related issues.

Plugins, steps, and tmt code in general can register hints to be shown
to user when an important (or optional, but interesting) package is not
available.

Hints are shown when importing plugins fails, and rendered as part of
both their CLI help and HTML documentation.
"""

# NOTE (happz): in my plan, this module would be an unfinished, staging
# area for hints; eventually, I would like them to be managed under the
# umbrella of `tmt about` subcommand. `print_hint()` would still exist,
# but `tmt about` would be responsible for handling hints, therefore the
# code below may change, the concept should not. And hints would cover
# wider area, e.g. describing common errors and issues, not just when
# a package is missing. They would be coupled with exceptions tmt
# raises, providing more info on command-line and in HTML docs.

import textwrap
from collections.abc import Iterator
from typing import Optional

import tmt.log
import tmt.utils
import tmt.utils.rest

HINTS: dict[str, str] = {
    # Hints must be dedented & stripped of leading/trailing white space.
    # For hints registered by plugins, this is done by `register_hint()`.
    _hint_id: textwrap.dedent(_hint).strip()
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

    HINTS[id_] = textwrap.dedent(hint).strip()


def render_hint(
    *, id_: str, ignore_missing: bool = False, logger: tmt.log.Logger
) -> Optional[str]:
    """
    Render a given hint to be printable.

    :param id_: id of the hint to render.
    :param ignore_missing: if not set, non-existent hints will
        raise an exception.
    :param logger: to use for logging.
    :returns: a printable representation of the hint. If the hint ID
        does not exist and ``ignore_missing`` is set, ``None`` is
        returned.
    """

    def _render_single_hint(hint: str) -> str:
        if tmt.utils.rest.REST_RENDERING_ALLOWED:
            return tmt.utils.rest.render_rst(hint, logger)

        return hint

    if ignore_missing:
        hint = HINTS.get(id_)

        if hint is None:
            return None

        return _render_single_hint(hint)

    hint = HINTS.get(id_)

    if hint is None:
        raise tmt.utils.GeneralError(f"Could not find hint '{id_}'.")

    return _render_single_hint(hint)


def render_hints(*ids: str, ignore_missing: bool = False, logger: tmt.log.Logger) -> str:
    """
    Render multiple hints into a single screen of text.

    :param ids: ids of hints to render.
    :param ignore_missing: if not set, non-existent hints will
        raise an exception. Otherwise, non-existent hints will
        be skipped.
    :param logger: to use for logging.
    :returns: a printable representation of hints.
    """

    def _render_single_hint(hint: str) -> str:
        if tmt.utils.rest.REST_RENDERING_ALLOWED:
            return tmt.utils.rest.render_rst(hint, logger)

        return hint

    if ignore_missing:

        def _render_optional_hints() -> Iterator[str]:
            for id_ in ids:
                hint = HINTS.get(id_)

                if hint is None:
                    continue

                yield _render_single_hint(hint)

        return '\n'.join(_render_optional_hints())

    def _render_mandatory_hints() -> Iterator[str]:
        for id_ in ids:
            hint = HINTS.get(id_)

            if hint is None:
                raise tmt.utils.GeneralError(f"Could not find hint '{id_}'.")

            yield _render_single_hint(hint)

    return '\n'.join(_render_mandatory_hints())


def print_hint(*, id_: str, ignore_missing: bool = False, logger: tmt.log.Logger) -> None:
    """
    Display a given hint by printing it as a warning.

    :param id_: id of the hint to render.
    :param ignore_missing: if not set, non-existent hints will
        raise an exception.
    :param logger: to use for logging.
    """

    hint = render_hint(id_=id_, ignore_missing=ignore_missing, logger=logger)

    if hint is None:
        return

    logger.info(
        'hint', render_hint(id_=id_, ignore_missing=ignore_missing, logger=logger), color='blue'
    )
