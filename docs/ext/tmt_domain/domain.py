import typing

from sphinx.domains import Domain

if typing.TYPE_CHECKING:
    from docutils import nodes
    from sphinx.addnodes import pending_xref
    from sphinx.builders import Builder
    from sphinx.environment import BuildEnvironment


class TmtDomain(Domain):
    name = "tmt"
    label = "Internal tmt sphinx domain"
    roles = {}
    directives = {}
    indices = []
    data_version = 0

    def resolve_any_xref(
        self,
        env: "BuildEnvironment",
        fromdocname: str,
        builder: "Builder",
        target: str,
        node: "pending_xref",
        contnode: "nodes.Element",
    ) -> list[tuple[str, "nodes.reference"]]:
        # TODO: Convert the current :ref:`/plugins/...` for easier transition
        return []
