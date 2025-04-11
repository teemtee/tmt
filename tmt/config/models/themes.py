from typing import Any, Optional, Union

# TID251: this use of `click.style()` is expected, and on purpose.
from click import style as _style  # noqa: TID251

import tmt.utils
from tmt._compat.pydantic import ValidationError
from tmt._compat.typing import TypeAlias
from tmt.container import MetadataContainer

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

        return _style(text, **self.dict())


_DEFAULT_STYLE = Style()


class Theme(MetadataContainer):
    """
    A collection of items tmt uses to colorize various tokens of its CLI.
    """

    restructuredtext_text: Style = _DEFAULT_STYLE

    restructuredtext_literal: Style = _DEFAULT_STYLE
    restructuredtext_emphasis: Style = _DEFAULT_STYLE
    restructuredtext_strong: Style = _DEFAULT_STYLE

    restructuredtext_literalblock: Style = _DEFAULT_STYLE
    restructuredtext_literalblock_yaml: Style = _DEFAULT_STYLE
    restructuredtext_literalblock_shell: Style = _DEFAULT_STYLE

    restructuredtext_admonition_note: Style = _DEFAULT_STYLE
    restructuredtext_admonition_warning: Style = _DEFAULT_STYLE

    def to_spec(self) -> dict[str, Any]:
        return {key.replace('_', '-'): value for key, value in self.dict().items()}

    def to_minimal_spec(self) -> dict[str, Any]:
        spec: dict[str, Any] = {}

        for theme_key, style in self.to_spec().items():
            style_spec = {
                style_key: value for style_key, value in style.items() if value is not None
            }

            if style_spec:
                spec[theme_key] = style_spec

        return spec

    @classmethod
    def from_spec(cls: type['Theme'], data: Any) -> 'Theme':
        try:
            return Theme.parse_obj(data)

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
