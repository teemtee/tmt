from typing import TYPE_CHECKING, Optional, Union

# TID251: this use of `click.style()` is expected, and on purpose.
from click import style as _style  # noqa: TID251

if TYPE_CHECKING:
    from tmt.config.models.themes import Style as ThemeStyle


#: A style to apply to a string.
#:
#: .. note::
#:
#:    Eventually, this would be :py:class:`ThemeStyle`. For now, we need
#:    to allow the Colorama color specification, strings.
Style = Union[None, str, 'ThemeStyle']


def style(
    s: str,
    *,
    style: Style = None,
    fg: Optional[str] = None,
    bold: bool = False,
    underline: bool = False,
) -> str:
    """
    Apply a style to a string.

    ``style`` is the most preferred argument, and, if set, no other
    arguments would be used. If ``style`` is not given, remaining keyword
    arguments are passed directly to :py:func:`click.style`.

    :param s: string to colorize.
    :param style: style to apply. If set, it will be preferred over any
        other arguments.
    :param fg: foreground color.
    :param bold: whether the text should be using bold font.
    :param underline: whether the text should be underlined.
    :returns: colorized string.
    """

    if style is None:
        _colorama_kwargs = {'fg': fg, 'bold': bold, 'underline': underline}

        if _colorama_kwargs:
            return _style(
                s,
                **_colorama_kwargs,  # type: ignore[reportArgumentType,arg-type,unused-ignore]
            )

        return s

    from tmt.config.models.themes import Style as ThemeStyle

    if isinstance(style, ThemeStyle):
        return style.apply(s)

    return _style(s, fg=fg)
