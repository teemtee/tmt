from typing import Generic, TypeVar

from fmf.context import Context, ContextDimension, DefaultContextDimension

import tmt.utils
from tmt.plugins import PluginRegistry

T = TypeVar("T")


class ContextError(tmt.utils.GeneralError):
    """
    Error trying to create a context
    """


class TmtDefaultContextDimension(DefaultContextDimension):
    case_sensitive = False


class TmtContextDimension(ContextDimension[T], Generic[T]):
    _default_dimension_cls = TmtDefaultContextDimension
    _registrar = {}


class TmtContext(Context):
    _context_dimensions = TmtContextDimension


_CONTEXT_REGISTRY = PluginRegistry('context')
provides_context = _CONTEXT_REGISTRY.create_decorator()
