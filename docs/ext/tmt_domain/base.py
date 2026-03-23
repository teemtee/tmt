"""
Base definitions for the tmt sphinx domain.

The base directives are split into a:
 * :py:class:`TmtObjectDirective` describing the sphinx object being documented
   and interacting primarily with the sphinx documenter.
 * :py:class:`TmtAutodocDirective` constructing the contents to be used by the
   :py:class:`TmtObjectDirective` from real tmt objects.

This split is similar to the python sphinx domain workflow.
"""

import abc
import typing
from functools import cached_property
from typing import Generic, Optional

from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.directives import ObjDescT, ObjectDescription
from sphinx.roles import XRefRole
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

import tmt
from tmt._compat.pathlib import Path

from .autodoc import AutodocDirectiveBase

if typing.TYPE_CHECKING:
    from docutils.nodes import Element, Node, TextElement, system_message

    from .domain import TmtDomain


logger = logging.getLogger(__name__)


class TmtDirective(SphinxDirective, abc.ABC):
    """
    The base for all directives under the tmt sphinx domain.
    """

    @cached_property
    def tmt_domain(self) -> "TmtDomain":
        """
        Tmt domain object of the current sphinx project.
        """
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
    # TODO: Figure out what the ObjDescT should point to
    # Note: Cannot always use this directive because it implies a very specific
    # format of the output html object e.g. requiring a signature node.
    # https://github.com/sphinx-doc/sphinx/issues/14042
    """
    Base directive describing a tmt object.

    The documented tmt object is that of
    :py:attr:`tmt_domain.domain.TmtDomain.objects`, and represent the abstract
    description of the tmt object. The object being described may not represent
    a real tmt object.
    """


#: Actual tmt object being documented
TmtObjT = typing.TypeVar('TmtObjT')


class TmtAutodocDirective(
    AutodocDirectiveBase,
    TmtDirective,
    abc.ABC,
    Generic[TmtObjT],
):
    """
    Base directive for documenting a real tmt object.

    The purpose of these directives is to process the real tmt object and
    generate its documentation in an RST format to be consumed by an equivalent
    :py:class:`TmtObjectDirective` directive.
    """

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


class TmtXRefRole(XRefRole):
    """
    Base tmt role for cross-referencing to a tmt object.

    This saves some additional options indicating how to expand the role during the
    call to :py:meth:`sphinx.domains.Domain.resolve_xref`.
    """

    #: Whether to use the tmt object's name/title key instead of the address
    use_obj_name: bool = False

    def __init__(
        self,
        fix_parens: bool = False,
        lowercase: bool = False,
        nodeclass: Optional[type["Element"]] = None,
        innernodeclass: Optional[type["TextElement"]] = None,
        warn_dangling: bool = False,
        use_obj_name: Optional[bool] = None,
    ) -> None:
        if use_obj_name is not None:
            self.use_obj_name = use_obj_name
        super().__init__(
            fix_parens=fix_parens,
            lowercase=lowercase,
            nodeclass=nodeclass,
            innernodeclass=innernodeclass,
            warn_dangling=warn_dangling,
        )

    def create_xref_node(self) -> tuple[list["Node"], list["system_message"]]:
        # We do not have access to the actual tmt object until `Domain.resolve_xref` is
        # being executed. We can only save the intent in the pending_xref node's data
        # and handle it accordingly in the `resolve_xref`. See similar logic used with
        # `refexplicit` (`sphinx.domains.std`)
        nodes, messages = super().create_xref_node()
        ref_node = nodes[0]
        assert isinstance(ref_node, addnodes.pending_xref)
        ref_node["tmtrefuseobjname"] = self.use_obj_name
        return nodes, messages
