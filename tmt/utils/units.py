"""
Shared unit registry.

The Pint :class:`~pint.UnitRegistry` used to live in
:mod:`tmt.hardware.constraints` because it was only needed for hardware
size specifications. It is now also used for generic quantities such as
log size limits and cache age, so it lives here to avoid coupling
non-hardware code to :mod:`tmt.hardware`.
"""

from typing import TYPE_CHECKING

import pint

if TYPE_CHECKING:
    from tmt._compat.typing import TypeAlias

    #: A type of values describing sizes of things like storage or RAM.
    # Note: type-hinting is a bit wonky with pyright
    # https://github.com/hgrecco/pint/issues/1166
    Size: TypeAlias = pint.Quantity

#: Unit registry, used and shared by all code.
UNITS = pint.UnitRegistry()

# The default formatting should use unit symbols rather than full names.
# reportDeprecated: in some Pint versions, this method is deprecated.
UNITS.default_format = '~'  # type: ignore[reportDeprecated,unused-ignore]
