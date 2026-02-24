"""
Main definition of the ``tmt`` domain.
"""

import typing
from collections.abc import Iterable
from functools import cached_property

from docutils import nodes
from sphinx.domains import Domain, ObjType
from sphinx.util import logging
from sphinx.util.nodes import make_refnode

import tmt
import tmt.log

from .base import TmtXRefRole
from .story import AutoStoryDirective, StoryDirective, StoryIndex

if typing.TYPE_CHECKING:
    from sphinx.addnodes import pending_xref
    from sphinx.builders import Builder
    from sphinx.domains import IndexEntry
    from sphinx.environment import BuildEnvironment

    from tmt._compat.pathlib import Path


logger = logging.getLogger(__name__)


class TmtDomain(Domain):
    """
    Sphinx domain for documenting and referencing tmt objects.

    For more details see :ref:`tutorial-adding-domain`, and the upstream
    implementations of :py:class:`sphinx.domains.Domain`,
    :py:class`sphinx.domains.python.PythonDomain`.
    """

    # Required attributes to setup the domain.
    name = "tmt"
    label = "Internal tmt sphinx domain"
    roles = {
        "story": TmtXRefRole(use_obj_name=True),
    }
    directives = {
        "autostory": AutoStoryDirective,
        "story": StoryDirective,
    }
    indices = [
        StoryIndex,
    ]
    object_types = {
        "story": ObjType("story", "story"),
    }
    initial_data = {
        "objects": {},
        "tmt_trees": {},
    }
    data_version = 0

    # tmt domain specific helper functions.
    @cached_property
    def tmt_logger(self) -> tmt.log.Logger:
        """
        Tmt logger adjusted to work with Sphinx's logger.
        """
        # TODO: Figure out how to pass it the logger.logger and how to skip all the messages
        return tmt.log.Logger.create(quiet=True)

    @property
    def tmt_trees(self) -> dict["Path", tmt.Tree]:
        """
        Tmt trees being processed in the current sphinx project.

        The keys are the paths to the root of the tmt trees, or any other
        paths under it. Many paths can point to the same tmt tree object.
        """
        return self.data.setdefault("tmt_trees", {})

    @property
    def objects(self) -> dict[str, dict[str, "IndexEntry"]]:
        """
        Sphinx objects being documented.

        This mimics :py:attr:`sphinx.domains.python.PythonDomain.objects`,
        with an additional layer.

        The outermost dict structure is:
          * key: the type of objects documented, related to
            :py:attr`object_types` keys
          * value: a dict of documented objects of the given type

        The inner dict structure is:
          * key: the canonical name of the object as referenced by the roles
          * value: the object's referencing information
        """
        # TODO: The objects should belong to a tmt tree
        return self.data.setdefault("objects", {})

    def note_object(self, typ: str, name: str, entry: "IndexEntry") -> None:
        """
        Record a documented object's referencing information.

        This mimics :py:attr`sphinx.domains.python.PythonDomain.note_object`.

        :param typ: the object's type as used in :py:attr:`objects`
        :param name: the object's canonical name as used in :py:attr:`objects`
        :param entry: the object's referencing information
        """
        typ_objects = self.objects.setdefault(typ, {})
        other_object = typ_objects.get(name)
        if other_object:
            logger.warning(
                f"Duplicate '{name}' ({typ}) object is being described. "
                f"Other instance in {other_object.docname}."
            )
        typ_objects[name] = entry

    # Overrides of necessary Domain methods.
    def resolve_xref(
        self,
        env: "BuildEnvironment",
        fromdocname: str,
        builder: "Builder",
        typ: str,
        target: str,
        node: "pending_xref",
        contnode: "nodes.Element",
    ) -> typing.Optional["nodes.reference"]:
        obj_types = self.objtypes_for_role(typ)
        assert len(obj_types) == 1, (
            "In tmt domain we have one-to-one relation between role and ObjType."
        )
        # Get the sub-dict of objects of the current type
        typ_objects = self.objects.get(obj_types[0], {})
        if not (obj := typ_objects.get(target)):
            return None
        # Fix title from the actual object's title if needed.
        # - `tmtrefuseobjname` aka `use_obj_name` is defined for each `TmtXRefRole` and
        #   specifies if we want to use the tmt object's name/title (saved as `obj.name`)
        # - `refexplicit` aka `has_explicit_title` is `True` if the role was defined like
        #   :tmt:story:`Other title</spec/plans>` (we do not need to change the title then)
        if node.get("tmtrefuseobjname", False) and not node.get("refexplicit", False):
            contnode.pop(0)
            contnode += nodes.Text(obj.name)
        return make_refnode(
            builder=builder,
            fromdocname=fromdocname,
            todocname=obj.docname,
            targetid=obj.anchor,
            child=contnode,
            title=obj.name,
        )

    def get_objects(self) -> Iterable[tuple[str, str, str, str, str, int]]:
        for typ, typ_objects in self.objects.items():
            for obj_name, obj in typ_objects.items():
                # TODO: Is the correct display name being shown?
                # TODO: What should be the priority for each object?
                yield obj_name, obj.name, typ, obj.docname, obj.anchor, 1

    def resolve_any_xref(
        self,
        env: "BuildEnvironment",
        fromdocname: str,
        builder: "Builder",
        target: str,
        node: "pending_xref",
        contnode: "nodes.Element",
    ) -> list[tuple[str, "nodes.reference"]]:
        results = []
        for typ in self.objects:
            ref = self.resolve_xref(env, fromdocname, builder, typ, target, node, contnode)
            if ref:
                results.append((self.role_for_objtype(typ), ref))
        return results

    def clear_doc(self, docname: str) -> None:
        # Clear object inventory
        for typ, typ_objects in self.objects.items():
            to_remove = []
            for obj_name, obj in typ_objects.items():
                if obj.docname == docname:
                    to_remove.append(obj_name)
            for obj_name in to_remove:
                del self.objects[typ][obj_name]

    def merge_domaindata(self, docnames: set[str], otherdata: dict[str, typing.Any]) -> None:
        # Merge objects data
        for typ, typ_objects in otherdata["objects"].items():
            for obj_name, obj in typ_objects.items():
                if obj.docname in docnames:
                    self.objects[typ][obj_name] = obj
        # Merge tmt trees
        for path, tree in otherdata["tmt_trees"].items():
            # tmt trees are not linked to specific documents so just merge whatever we have
            if path not in self.tmt_trees:
                # TODO: Should handle duplicates better here
                self.tmt_trees[path] = tree
