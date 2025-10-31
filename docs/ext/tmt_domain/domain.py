import typing
from collections.abc import Iterable
from functools import cached_property

from docutils import nodes
from sphinx.domains import Domain, ObjType
from sphinx.util import logging
from sphinx.util.nodes import find_pending_xref_condition, make_refnode

import tmt
import tmt.log

if typing.TYPE_CHECKING:
    from sphinx.addnodes import pending_xref
    from sphinx.builders import Builder
    from sphinx.domains import IndexEntry
    from sphinx.environment import BuildEnvironment

    from tmt._compat.pathlib import Path


logger = logging.getLogger(__name__)


class TmtDomain(Domain):
    name = "tmt"
    label = "Internal tmt sphinx domain"
    roles = {}
    directives = {}
    indices = []
    object_types = {}
    initial_data = {
        "objects": {},
        "tmt_trees": {},
    }
    data_version = 0

    @cached_property
    def tmt_logger(self) -> tmt.log.Logger:
        # TODO: Figure out how to pass it the logger.logger and how to skip all the messages
        return tmt.log.Logger.create(quiet=True)

    @property
    def tmt_trees(self) -> dict["Path", tmt.Tree]:
        return self.data.setdefault("tmt_trees", {})

    @property
    def objects(self) -> dict[str, dict[str, "IndexEntry"]]:
        # TODO: The objects should belong to a tmt tree
        return self.data.setdefault("objects", {})

    def note_object(self, typ: str, name: str, entry: "IndexEntry") -> None:
        typ_objects = self.objects.setdefault(typ, {})
        other_object = typ_objects.get(name)
        if other_object:
            logger.warning(
                f"Duplicate '{name}' ({typ}) object is being described. "
                f"Other instance in {other_object.docname}."
            )
        typ_objects[name] = entry

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
        # Fix title from the actual object's title.
        # Check `refexplicit` aka `has_explicit_title` if we actually need to do it.
        if not node.get("refexplicit", False):
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
            # tmt trees are not linked to specific documents so just merge wathereve we have
            if path not in self.tmt_trees:
                # TODO: Should handle duplicates better here
                self.tmt_trees[path] = tree
