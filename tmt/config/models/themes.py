from typing import Any, Optional, Union, cast

# TID251: this use of `click.style()` is expected, and on purpose.
from click import style as _style  # noqa: TID251

import tmt.utils
from tmt._compat.pydantic import ValidationError
from tmt._compat.typing import TypeAlias
from tmt.container import MetadataContainer, metadata_field

Color: TypeAlias = Union[int, tuple[int, int, int], str, None]


class Style(MetadataContainer):
    """
    A collection of parameters accepted by :py:func:`click.style`.
    """

    fg: Optional[Color] = None
    bg: Optional[Color] = None
    bold: Optional[bool] = None
    dim: Optional[bool] = None
    underline: Optional[bool] = None
    italic: Optional[bool] = None
    blink: Optional[bool] = None
    strikethrough: Optional[bool] = None

    def apply(self, text: str) -> str:
        """
        Apply this style to a given string.
        """

        return _style(text, **self.model_dump())


_DEFAULT_STYLE = Style()


class _Theme(MetadataContainer):
    def get_style(self, field: str) -> Style:
        """
        Return a style when the field name is dynamic.

        A safer, type-annotated variant of ``getattr(theme, field)``.
        """

        if field not in self.model_fields_set:
            raise tmt.utils.GeneralError(
                f"No such theme field '{self.__class__.__name__.lower()}.{field}'."
            )

        # Using model_fields is deprecated and will be removed in pydantic v3
        # If we can convert this to class method then we can avoid this issue.
        if self.model_fields[field].annotation is not Style:  # pyright: ignore[reportDeprecated]
            raise tmt.utils.GeneralError(
                f"Theme field '{self.__class__.__name__.lower()}.{field}' is not a style."
            )

        return cast(Style, getattr(self, field))


class LinterOutcome(_Theme):
    """
    Styles for outcomes of various linter rules.
    """

    skip: Style = _DEFAULT_STYLE
    # We cannot use `pass` as an attribute name.
    pass_: Style = metadata_field(default=_DEFAULT_STYLE, alias='pass')
    fail: Style = _DEFAULT_STYLE
    warn: Style = _DEFAULT_STYLE
    fixed: Style = _DEFAULT_STYLE

    # Thanks to `pass` being a keyword, we need to map `LinterOutcome.PASS.value`,
    # which is "pass", to "pass_" than can be used as an object attribute.
    def get_style(self, field: str) -> Style:
        return super().get_style('pass_' if field == 'pass' else field)


class Linter(_Theme):
    """
    Styles for linter output.
    """

    outcome: LinterOutcome


class Theme(_Theme):
    """
    A collection of items tmt uses to colorize various tokens of its CLI.
    """

    linter: Linter

    restructuredtext_text: Style = _DEFAULT_STYLE

    restructuredtext_literal: Style = _DEFAULT_STYLE
    restructuredtext_emphasis: Style = _DEFAULT_STYLE
    restructuredtext_strong: Style = _DEFAULT_STYLE

    restructuredtext_literalblock: Style = _DEFAULT_STYLE
    restructuredtext_literalblock_yaml: Style = _DEFAULT_STYLE
    restructuredtext_literalblock_shell: Style = _DEFAULT_STYLE

    restructuredtext_admonition_note: Style = _DEFAULT_STYLE
    restructuredtext_admonition_warning: Style = _DEFAULT_STYLE

    @classmethod
    def from_spec(cls: type['Theme'], data: Any) -> 'Theme':
        try:
            return Theme.model_validate(data)

        except ValidationError as error:
            raise tmt.utils.SpecificationError("Invalid theme configuration.") from error

    @classmethod
    def from_file(cls: type['Theme'], path: tmt.utils.Path) -> 'Theme':
        return Theme.from_spec(tmt.utils.yaml_to_dict(path.read_text()))


class ThemeConfig(MetadataContainer):
    active_theme: str = 'default'

    @classmethod
    def load_theme(cls, theme_name: str) -> Theme:
        try:
            return Theme.from_file(
                tmt.utils.resource_files(tmt.utils.Path('config/themes') / f'{theme_name}.yaml')
            )

        except FileNotFoundError as exc:
            raise tmt.utils.GeneralError(f"No such theme '{theme_name}'.") from exc

    @classmethod
    def get_default_theme(cls) -> Theme:
        return cls.load_theme('default')

    def get_active_theme(self) -> Theme:
        return self.load_theme(self.active_theme)
