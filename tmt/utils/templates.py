"""
Template rendering.

Package provides primitives for Jinja2 template rendering, plus our
custom filters.
"""

import re
import textwrap
from re import Match
from typing import (
    Any,
    Callable,
    Optional,
    cast,
    )

import fmf
import fmf.utils
import jinja2
import jinja2.exceptions

from tmt.utils import GeneralError, Path
from tmt.utils.git import web_git_url


def _template_filter_basename(  # type: ignore[reportUnusedFunction,unused-ignore]
        pathlike: str) -> str:
    """
    Return the last component of the given path.

    .. code-block:: jinja

        # "/etc/fstab" -> "fstab"
        {{ "/etc/fstab" | basename }}

        # "/var/log/" -> "log"
        {{ "/var/log/" | basename }}
    """

    return Path(pathlike).name


def _template_filter_match(  # type: ignore[reportUnusedFunction,unused-ignore]
        s: str, pattern: str) -> Optional[Match[str]]:
    """
    Return `re.Match`__ if the string matches a given pattern.

    Pattern is tested in "match" mode, i.e. it must match from the
    beginning of the string. See :ref:`regular-expressions` description
    for more details.

    __ https://docs.python.org/3.9/library/re.html#match-objects

    .. code-block:: jinja

         # 'foo/bar' -> 'foo/bar'
        {{ 'foo/bar' | match('foo/.*').group() }}

        # 'foo/bar' -> ''
        {{ 'foo/bar' | match('foo/(.+?)/(.*)') }}

        # 'foo/bar/baz' -> 'bar'
        {{ 'foo/bar' | match('foo/(.+?)/.*').group(1) }}
    """

    return re.match(pattern, s)


def _template_filter_search(  # type: ignore[reportUnusedFunction,unused-ignore]
        s: str, pattern: str) -> Optional[Match[str]]:
    """
    Return `re.Match`__ if the string matches a given pattern.

    Pattern is tested in "search" mode, i.e. it can match anywhere
    in the string. See :ref:`regular-expressions` description for more
    details.

    __ https://docs.python.org/3.9/library/re.html#match-objects

    .. code-block:: jinja

         # 'baz/foo/bar' -> 'foo/bar'
        {{ 'baz/foo/bar' | search('foo/.*').group() }}

        # 'baz/foo/bar' -> ''
        {{ 'baz/foo/bar' | search('foo/(.+?)/(.*)') }}

        # 'baz/foo/bar/baz' -> 'bar'
        {{ 'baz/foo/bar' | search('foo/(.+?)/.*').group(1) }}
    """

    return re.search(pattern, s)


def _template_filter_regex_findall(  # type: ignore[reportUnusedFunction,unused-ignore]
        s: str, pattern: str) -> list[str]:
    """
    Return a list of all non-overlapping matches in the string.

    If one or more capturing groups are present in the pattern, return
    a list of groups; this will be a list of tuples if the pattern
    has more than one group.

    Empty matches are included in the result.

    .. code-block:: jinja

        # '/var/log/mail.log' => ['/', '/', '/']
        {{ '/var/log/mail.log' | regex_findall('/') }}
    """

    return re.findall(pattern, s)


def _template_filter_regex_match(  # type: ignore[reportUnusedFunction,unused-ignore]
        s: str, pattern: str) -> str:
    """
    Return string matching a given pattern.

    Pattern is tested in "match" mode, i.e. it must match from the
    beginning of the string. See :ref:`regular-expressions` description
    for more details.

    If the string matches and pattern contains capture groups, the
    first group is returned. If the string matches, but patterns
    contains no capture group, the whole match is returned.
    Otherwise, an empty string is returned.

    .. code-block:: jinja

        # 'foo/bar' -> 'foo/bar'
        {{ 'foo/bar' | regex_match('foo/.*') }}

        # 'foo/bar' -> ''
        {{ 'foo/bar' | regex_match('foo/(.+?)/(.*)') }}

        # 'foo/bar/baz' -> 'bar'
        {{ 'foo/bar/baz' | regex_match('foo/(.+?)/.*') }}
    """

    match = re.match(pattern, s)

    if match is None:
        return ''

    if not match.groups():
        return match.group()

    return match.group(1)


def _template_filter_regex_search(  # type: ignore[reportUnusedFunction,unused-ignore]
        s: str, pattern: str) -> str:
    """
    Return string matching a given pattern.

    Pattern is tested in "search" mode, i.e. it can match anywhere
    in the string. See :ref:`regular-expressions` description for more
    details.

    If the string matches and pattern contains capture groups, the
    first group is returned. If the string matches, but patterns
    contains no capture group, the whole match is returned.
    Otherwise, an empty string is returned.

    .. code-block:: jinja

        # 'baz/foo/bar' -> 'foo/bar'
        {{ 'baz/foo/bar' | regex_search('foo/.*') }}

        # 'baz/foo/bar' -> ''
        {{ 'baz/foo/bar' | regex_search('foo/(.+?)/(.*)') }}

        # 'baz/foo/bar/baz' -> 'bar'
        {{ 'baz/foo/bar/baz' | regex_search('foo/(.+?)/.*') }}
    """

    match = re.search(pattern, s)

    if match is None:
        return ''

    if not match.groups():
        return match.group()

    return match.group(1)


def _template_filter_regex_replace(  # type: ignore[reportUnusedFunction,unused-ignore]
        s: str, pattern: str, repl: str) -> str:
    """
    Replace a substring defined by a regular expression with another string.

    Return the string obtained by replacing the leftmost
    non-overlapping occurrences of pattern in string by the replacement.
    If the pattern isn't found, string is returned unchanged.

    Backreferences in the replacement string are replaced with the
    substring matched by a group in the pattern.

    .. code-block:: jinja

        # 'foo/bar' -> 'foo/baz'
        {{ 'foo/bar' | regex_replace('(.+)/bar', '\1/baz') }}

        # 'foo/bar' -> 'foo/bar'
        {{ 'foo/bar' | regex_replace('(.+)/baz', '\1/') }}
    """

    return re.sub(pattern, repl, s)


def _template_filter_dedent(s: str) -> str:  # type: ignore[reportUnusedFunction,unused-ignore]
    """
    Remove any common leading whitespace from every line in the string.

    .. code-block:: jinja

        # "foo bar" -> "foo bar"
        {{ "foo bar" | dedent }}

        # '''
        #    foo
        #    bar
        #        baz
        # '''
        #  ->
        # '''
        # foo
        # bar
        #    baz
        # '''
        {{ "\\n    foo\\n    bar\\n        baz\\n" | dedent }}
    """

    return textwrap.dedent(s)


def _template_filter_listed(  # type: ignore[reportUnusedFunction,unused-ignore]
        items: list[Any],
        singular: Optional[str] = None,
        plural: Optional[str] = None,
        max: Optional[int] = None,
        quote: str = "",
        join: str = "and") -> str:
    """
    Return a nice, human readable description of an iterable.

    .. code-block:: jinja

        # [0] -> "0"
        {{ [0] | listed }}

        # [0, 1] -> "0 and 1"
        {{ [0, 1] | listed }}

        # [0, 1, 2] -> "0, 1, or 2"
        {{ [0, 1, 2] | listed(join='or') }}

        # [0, 1, 2] -> '"0", "1" and "2"'
        {{ [0, 1, 2] | listed(quote='"') }}

        # [0, 1, 2, 3] -> "0, 1, 2 and 1 more"
        {{ [0, 1, 2, 3] | listed(max=3) }}

        # [0, 1, 2, 3, 4] -> "0, 1, 2 and 2 more numbers"
        {{ [0, 1, 2, 3, 4, 5] | listed('number', max=3) }}

        # [0, 1, 2, 3, 4, 5] -> "6 categories"
        {{ [0, 1, 2, 3, 4, 5] | listed('category') }}

        # [0, 1, 2, 3, 4, 5, 6] -> "7 leaves"
        {{ [0, 1, 2, 3, 4, 5, 6] | listed("leaf", "leaves") }}
    """

    # cast: for some reason, mypy sees `listed` as `Any`
    return cast(str, fmf.utils.listed(
        items,
        singular=singular,
        plural=plural,
        max=max,
        quote=quote,
        join=join))


def _template_filter_web_git_url(  # type: ignore[reportUnusedFunction,unused-ignore]
        path_str: str,
        url: str,
        ref: str) -> str:
    """
    Sanitize git url using :py:meth:`tmt.utils.web_git_url`

    .. code-block:: jinja

        {{ "/path/to/the/code.py" | web_git_url(STORY.fmf_id.url, STORY.fmf_id.ref) }}

        {{ "/tmt/base.py" | web_git_url("https://github.com/teemtee/tmt.git", "main") }}
        -> https://github.com/teemtee/tmt/tree/main/tmt/base.py

    """
    path = Path(path_str) if path_str else None
    return web_git_url(url, ref, path)


TEMPLATE_FILTERS: dict[str, Callable[..., Any]] = {
    _name.replace('_template_filter_', ''): _obj
    for _name, _obj in locals().items() if callable(_obj) and _name.startswith('_template_filter_')
    }


def _template_test_unit(value: Any) -> bool:  # type: ignore[reportUnusedFunction,unused-ignore]
    """
    Return true if the object is a unit.

    .. code-block:: jinja

        {% if value is unit %}
            Value is a Pint's ``Quantity`` instance.
        {% endif %}
    """

    from pint import Quantity

    return isinstance(value, Quantity)


TEMPLATE_TESTS: dict[str, Callable[..., Any]] = {
    _name.replace('_template_test_', ''): _obj
    for _name, _obj in locals().items() if callable(_obj) and _name.startswith('_template_test_')
    }


def default_template_environment() -> jinja2.Environment:
    """
    Create a Jinja2 environment with default settings.

    Adds common filters, and enables block trimming and left strip.
    """

    # S701: `autoescape=False` is dangerous and can lead to XSS.
    # As there can be many different template file formats, used to render various formats,
    # we need to explicitly set autoescape=False, as default might change in the future.
    # Potential improvements are being tracked in /teemtee/tmt/issues/2873

    environment = jinja2.Environment()  # noqa: S701

    environment.filters.update(TEMPLATE_FILTERS)
    environment.tests.update(TEMPLATE_TESTS)

    environment.trim_blocks = True
    environment.lstrip_blocks = True

    return environment


def render_template(
        template: str,
        template_filepath: Optional[Path] = None,
        environment: Optional[jinja2.Environment] = None,
        **variables: Any
        ) -> str:
    """
    Render a template.

    :param template: template to render.
    :param template_filepath: path to the template file, if any.
    :param environment: Jinja2 environment to use.
    :param variables: variables to pass to the template.
    """

    environment = environment or default_template_environment()

    def raise_error(message: str) -> None:
        """ An in-template helper for raising exceptions """

        raise Exception(message)

    if 'raise_error' not in variables:
        variables['raise_error'] = raise_error

    try:
        return environment.from_string(template).render(**variables).strip()

    except jinja2.exceptions.TemplateSyntaxError as exc:
        if template_filepath:
            raise GeneralError(
                f"Could not parse template '{template_filepath}' at line {exc.lineno}.") from exc
        raise GeneralError(
            f"Could not parse template at line {exc.lineno}.") from exc

    except jinja2.exceptions.TemplateError as exc:
        if template_filepath:
            raise GeneralError(
                f"Could not render template '{template_filepath}'.") from exc
        raise GeneralError("Could not render template.") from exc


def render_template_file(
        template_filepath: Path,
        environment: Optional[jinja2.Environment] = None,
        **variables: Any
        ) -> str:
    """
    Render a template from a file.

    :param template_filepath: path to the template file.
    :param environment: Jinja2 environment to use.
    :param variables: variables to pass to the template.
    """

    try:
        return render_template(
            template_filepath.read_text(), template_filepath, environment, **variables)

    except FileNotFoundError as exc:
        raise GeneralError(
            f"Could not open template '{template_filepath}'.") from exc
