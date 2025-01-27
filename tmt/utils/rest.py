"""
ReST rendering.

Package provides primitives for ReST rendering used mainly for CLI
help texts.
"""

import functools
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Optional

import click
import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.parsers.rst.roles
import docutils.parsers.rst.states
import docutils.utils

import tmt.log
from tmt.log import Logger
from tmt.utils import GeneralError

# We may be sharing parser structures with Sphinx, when it's generating
# docs. And that lead to problems, our roles conflicting with those
# registered by Sphinx, or parser calling Sphinx roles in our context.
# Both Sphinx and docutils rely on global mutable states, and
# monkeypatching it around our calls to parser does not work. To avoid
# issues, ReST renderign is disabled when we know our code runs under
# the control of Sphinx.
REST_RENDERING_ALLOWED = ('sphinx-build' not in sys.argv[0])


#: Special string representing a new-line in the stack of rendered
#: paragraphs.
NL = ''


class RestVisitor(docutils.nodes.NodeVisitor):
    """
    Custom renderer of docutils nodes.

    See :py:class:`docutils.nodes.NodeVisitor` for details, but the
    functionality is fairly simple: for each node type, a pair of
    methods is expected, ``visit_$NODE_TYPE`` and ``depart_$NODE_TYPE``.
    As the visitor class iterates over nodes in the document,
    corresponding methods are called. These methods render the given
    node, filling "rendered paragraphs" list with rendered strings.
    """

    def __init__(self, document: docutils.nodes.document, logger: Logger) -> None:
        super().__init__(document)

        self.logger = logger
        self.debug = functools.partial(logger.debug, level=4, topic=tmt.log.Topic.HELP_RENDERING)
        self.log_visit = functools.partial(
            logger.debug, 'visit', level=4, topic=tmt.log.Topic.HELP_RENDERING)
        self.log_departure = functools.partial(
            logger.debug, 'depart', level=4, topic=tmt.log.Topic.HELP_RENDERING)

        #: Collects all rendered paragraps - text, blocks, lists, etc.
        self._rendered_paragraphs: list[str] = []
        #: Collect components of a single paragraph - sentences, literals,
        #: list items, etc.
        self._rendered_paragraph: list[str] = []

        self.in_literal_block: bool = False
        self.in_note: bool = False
        self.in_warning: bool = False

        #: Used by rendering of nested blocks, e.g. paragraphs positioned
        #: as list items.
        self._indent: int = 0
        self._text_prefix: Optional[str] = None

    @property
    def rendered(self) -> str:
        """ Return the rendered document as a single string """

        # Drop any trailing empty lines
        while self._rendered_paragraphs and self._rendered_paragraphs[-1] == NL:
            self._rendered_paragraphs.pop(-1)

        return '\n'.join(self._rendered_paragraphs)

    def _emit(self, s: str) -> None:
        """ Add a string to the paragraph being rendered """

        self._rendered_paragraph.append(s)

    def _emit_paragraphs(self, paragraphs: list[str]) -> None:
        """ Add new rendered paragraphs """

        self._rendered_paragraphs += paragraphs

    def flush(self) -> None:
        """ Finalize rendering of the current paragraph """

        if not self._rendered_paragraph:
            self.nl()

        else:
            self._emit_paragraphs([''.join(self._rendered_paragraph)])
            self._rendered_paragraph = []

    def nl(self) -> None:
        """ Render a new, empty line """

        # To simplify the implementation, this is merging of multiple
        # empty lines into one. Rendering of nodes than does not have
        # to worry about an empty line already being on the stack.
        if self._rendered_paragraphs and self._rendered_paragraphs[-1] != NL:
            self._emit_paragraphs([NL])

    # Simple logging for nodes that have no effect
    def _noop_visit(self, node: docutils.nodes.Node) -> None:
        self.log_visit(str(node))

    def _noop_departure(self, node: docutils.nodes.Node) -> None:
        self.log_departure(str(node))

    # Node renderers
    visit_document = _noop_visit

    def depart_document(self, node: docutils.nodes.document) -> None:
        self.log_departure(str(node))

        self.flush()

    def visit_paragraph(self, node: docutils.nodes.paragraph) -> None:
        self.log_visit(str(node))

        if isinstance(node.parent, docutils.nodes.list_item):
            if self._text_prefix:
                self._emit(self._text_prefix)
                self._text_prefix = None

            else:
                self._emit(' ' * self._indent)

        elif self.in_note:
            self._emit(click.style('NOTE: ', fg='blue', bold=True))
            return

        elif self.in_warning:
            self._emit(click.style('WARNING: ', fg='yellow', bold=True))
            return

    def depart_paragraph(self, node: docutils.nodes.paragraph) -> None:
        self.log_departure(str(node))

        # Top-level paragraphs should be followed by an empty line to
        # prevent paragraphs sticking together. Only the top-level ones
        # though, we do not want empty lines after every paragraph-like
        # string, because a lot of nodes are also paragraphs.
        if isinstance(node.parent, docutils.nodes.document):
            self.nl()

        self.flush()

    def visit_Text(self, node: docutils.nodes.Text) -> None:  # noqa: N802
        self.log_visit(str(node))

        if isinstance(node.parent, docutils.nodes.literal):
            return

        if self.in_literal_block:
            return

        if self.in_note:
            self._emit(click.style(node.astext(), fg='blue'))

            return

        if self.in_warning:
            self._emit(click.style(node.astext(), fg='yellow'))

            return

        self._emit(node.astext())

    depart_Text = _noop_departure  # noqa: N815

    def visit_literal(self, node: docutils.nodes.literal) -> None:
        self.log_visit(str(node))

        self._emit(click.style(node.astext(), fg='green'))

    depart_literal = _noop_departure

    def visit_literal_block(self, node: docutils.nodes.literal_block) -> None:
        self.log_visit(str(node))

        self.flush()

        fg: str = 'cyan'

        if 'yaml' in node.attributes['classes']:
            pass

        elif 'shell' in node.attributes['classes']:
            fg = 'yellow'

        self._emit_paragraphs([
            f'    {click.style(line, fg=fg)}' for line in node.astext().splitlines()
            ])

        self.in_literal_block = True

    def depart_literal_block(self, node: docutils.nodes.literal_block) -> None:
        self.log_departure(str(node))

        self.in_literal_block = False

        self.nl()

    def visit_bullet_list(self, node: docutils.nodes.bullet_list) -> None:
        self.log_visit(str(node))

        self.nl()

    def depart_bullet_list(self, node: docutils.nodes.bullet_list) -> None:
        self.log_departure(str(node))

        self.nl()

    def visit_list_item(self, node: docutils.nodes.list_item) -> None:
        self.log_visit(str(node))

        self._text_prefix = '* '
        self._indent += 2

    def depart_list_item(self, node: docutils.nodes.list_item) -> None:
        self.log_departure(str(node))

        self._indent -= 2

    visit_inline = _noop_visit
    depart_inline = _noop_departure

    visit_reference = _noop_visit
    depart_reference = _noop_departure

    def visit_note(self, node: docutils.nodes.note) -> None:
        self.log_visit(str(node))

        self.nl()
        self.in_note = True

    def depart_note(self, node: docutils.nodes.note) -> None:
        self.log_departure(str(node))

        self.in_note = False
        self.nl()

    def visit_warning(self, node: docutils.nodes.warning) -> None:
        self.log_visit(str(node))

        self.nl()
        self.in_warning = True

    def depart_warning(self, node: docutils.nodes.warning) -> None:
        self.log_departure(str(node))

        self.in_warning = False
        self.nl()

    def unknown_visit(self, node: docutils.nodes.Node) -> None:
        raise GeneralError(f"Unhandled ReST node '{node}'.")

    def unknown_departure(self, node: docutils.nodes.Node) -> None:
        raise GeneralError(f"Unhandled ReST node '{node}'.")


# Role handling works out of the box when building docs with Sphinx, but
# for CLI rendering, we use docutils directly, and we need to provide
# handlers for roles supported by Sphinx.
#
# It might be possible to reuse Sphinx implementation, but a brief
# reading of Sphinx source gives an impression of pretty complex code.
# And we don't need anything fancy, how hard could it be, right? See
# https://docutils.sourceforge.io/docs/howto/rst-roles.html
def role_ref(
    name: str,
    rawtext: str,
    text: str,
    lineno: int,
    inliner: docutils.parsers.rst.states.Inliner,
    options: Optional[Mapping[str, Any]] = None,
    content: Optional[Sequence[str]] = None) \
        -> tuple[Sequence[docutils.nodes.reference], Sequence[docutils.nodes.reference]]:
    """
    A handler for ``:ref:`` role.

    :returns: a simple :py:class:`docutils.nodes.Text` node with text of
        the "link": ``foo`` for both ``:ref:`foo``` and
        ``:ref:`foo</bar>```.
    """

    return ([docutils.nodes.reference(rawtext, text)], [])


def parse_rst(text: str) -> docutils.nodes.document:
    """ Parse a ReST document into docutils tree of nodes """

    docutils.parsers.rst.roles.register_local_role('ref', role_ref)

    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(components=components).get_default_values()
    document = docutils.utils.new_document('<rst-doc>', settings=settings)

    parser.parse(text, document)

    return document


def render_rst(text: str, logger: Logger) -> str:
    """ Render a ReST document """

    document = parse_rst(text)
    visitor = RestVisitor(document, logger)

    document.walkabout(visitor)

    return visitor.rendered
