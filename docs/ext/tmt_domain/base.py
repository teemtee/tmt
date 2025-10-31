import abc
import typing
from functools import cached_property
from typing import Generic

from docutils.parsers.rst import directives
from sphinx.directives import ObjDescT, ObjectDescription
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

import tmt
from tmt._compat.pathlib import Path

from .autodoc import AutodocDirectiveBase

if typing.TYPE_CHECKING:
    from .domain import TmtDomain


logger = logging.getLogger(__name__)


class TmtDirective(SphinxDirective, abc.ABC):
    @cached_property
    def tmt_domain(self) -> "TmtDomain":
        from .domain import TmtDomain

        domain = self.env.domains.get("tmt")
        assert isinstance(domain, TmtDomain)  # narrow type
        return domain


class TmtObjectDirective(
    ObjectDescription[ObjDescT],
    TmtDirective,
    abc.ABC,
    Generic[ObjDescT],
):
    pass


TmtObjT = typing.TypeVar('TmtObjT')


class TmtAutodocDirective(
    AutodocDirectiveBase,
    TmtDirective,
    abc.ABC,
    Generic[TmtObjT],
):
    required_arguments = 1
    option_spec = {
        "tmt_tree": directives.unchanged_required,
    }
    #: Tmt tree that owns :py:attr:`tmt_object`
    tmt_tree: tmt.Tree
    #: Main tmt object that is being documented
    tmt_object: TmtObjT

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._get_tmt_tree()
        try:
            self._get_tmt_object()
        except Exception as exc:
            logger.error(
                f"Could not get valid tmt object '{self.name}::{self.arguments[0]}' ({exc})",
                location=self.get_location(),
            )

    @cached_property
    def tmt_domain(self) -> "TmtDomain":
        from .domain import TmtDomain

        domain = self.env.domains.get("tmt")
        assert isinstance(domain, TmtDomain)  # narrow type
        return domain

    def _get_tmt_tree(self) -> None:
        """
        Get the :py:attr:`tmt_tree` from options or config value.
        """
        # TODO: Expose this as a config variable instead
        tree_path = Path(self.options.get("tmt_tree", self.env.srcdir))
        # Get the tree object and save it in the domain variables
        if not (tree := self.tmt_domain.tmt_trees.get(tree_path)):
            tree = tmt.Tree(path=tree_path, logger=self.tmt_domain.tmt_logger)
            if tree.root in self.tmt_domain.tmt_trees:
                tree = self.tmt_domain.tmt_trees[tree.root]
            else:
                self.tmt_domain.tmt_trees[tree.root] = tree
            self.tmt_domain.tmt_trees[tree_path] = tree
        self.tmt_tree = tree

    @abc.abstractmethod
    def _get_tmt_object(self) -> None:
        """
        Get the :py:attr:`tmt_object`
        """
        raise NotImplementedError
