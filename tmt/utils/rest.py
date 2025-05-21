"""
ReST rendering.

Package provides primitives for ReST rendering used mainly for CLI
help texts.
"""

import functools
import re
import sys
import textwrap
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Optional, Union

import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.parsers.rst.roles
import docutils.parsers.rst.states
import docutils.utils

import tmt.log
import tmt.utils
from tmt.config import Config
from tmt.log import Logger
from tmt.utils import GeneralError

if TYPE_CHECKING:
    from tmt.config.models.themes import Style

# We may be sharing parser structures with Sphinx, when it's generating
# docs. And that lead to problems, our roles conflicting with those
# registered by Sphinx, or parser calling Sphinx roles in our context.
# Both Sphinx and docutils rely on global mutable states, and
# monkeypatching it around our calls to parser does not work. To avoid
# issues, ReST renderign is disabled when we know our code runs under
# the control of Sphinx.
REST_RENDERING_ALLOWED = not sys.argv or (
    # Local `make docs` builds
    'sphinx-build' not in sys.argv[0]
    and 'sphinx-apidoc' not in sys.argv[0]
    # Read the docs calls Sphinx this way
    and 'sphinx/__main__.py' not in sys.argv[0]
)

#: Special string representing a new-line in the stack of rendered
#: paragraphs.
NL = ''

BREAK = '-' * tmt.utils.OUTPUT_WIDTH

ADMONITION_FOOTER = BREAK

NOTE_HEADER = f'---\u00a0NOTE\u00a0{"-" * (tmt.utils.OUTPUT_WIDTH - 9)}'
NOTE_FOOTER = ADMONITION_FOOTER

WARNING_HEADER = f'---\u00a0WARNING\u00a0{"-" * (tmt.utils.OUTPUT_WIDTH - 12)}'
WARNING_FOOTER = ADMONITION_FOOTER

REMOVE_ANSI_PATTERN = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')


class ANSIString(str):
    def __len__(self) -> int:
        if '\n' in self:
            raise ValueError('String contains multiple lines.')

        return len(REMOVE_ANSI_PATTERN.sub('', self))


class TextWrapper(textwrap.TextWrapper):
    def _split(self, text: str) -> list[str]:
        return [ANSIString(chunk) for chunk in super()._split(text)]


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

    def log_visit(self, node: Union[docutils.nodes.Node, docutils.nodes.Body]) -> None:
        self.logger.debug('visit ', str(node), level=4, topic=tmt.log.Topic.HELP_RENDERING)

    def log_departure(self, node: Union[docutils.nodes.Node, docutils.nodes.Body]) -> None:
        self.logger.debug('depart', str(node), level=4, topic=tmt.log.Topic.HELP_RENDERING)

    def __init__(self, document: docutils.nodes.document, logger: Logger) -> None:
        super().__init__(document)

        self.logger = logger
        self.debug = functools.partial(logger.debug, level=4, topic=tmt.log.Topic.HELP_RENDERING)

        #: Collects all rendered paragraps - text, blocks, lists, etc.
        self._rendered_paragraphs: list[str] = []
        #: Collect components of a single paragraph - sentences, literals,
        #: list items, etc.
        self._rendered_paragraph: list[str] = []

        self.in_literal_block: bool = False

        #: Used by rendering of nested blocks, e.g. paragraphs positioned
        #: as list items.
        self._indent: int = 0
        self._text_prefix: Optional[str] = None

        self._theme = Config(logger).theme
        self._style_stack: list[Style] = [self._theme.restructuredtext_text]

    @property
    def rendered(self) -> str:
        """
        Return the rendered document as a single string
        """

        # Drop any trailing empty lines
        while self._rendered_paragraphs and self._rendered_paragraphs[-1] == NL:
            self._rendered_paragraphs.pop(-1)

        return '\n'.join(self._rendered_paragraphs)

    def _emit(self, s: str) -> None:
        """
        Add a string to the paragraph being rendered
        """

        self._rendered_paragraph.append(ANSIString(s))

    def _emit_paragraphs(self, paragraphs: list[str]) -> None:
        """
        Add new rendered paragraphs
        """

        self._rendered_paragraphs += paragraphs

    def flush(self) -> None:
        """
        Finalize rendering of the current paragraph
        """

        if not self._rendered_paragraph:
            self.nl()

        else:
            self._emit_paragraphs(
                [
                    '\n'.join(
                        TextWrapper(
                            width=tmt.utils.OUTPUT_WIDTH - self._indent,
                            break_long_words=False,
                            drop_whitespace=True,
                            replace_whitespace=True,
                            break_on_hyphens=False,
                            tabsize=4,
                            initial_indent='',
                            subsequent_indent=' ' * self._indent,
                        ).wrap(''.join(self._rendered_paragraph))
                    ).strip()
                ]
            )

            self._rendered_paragraph = []

    def nl(self) -> None:
        """
        Render a new, empty line
        """

        # To simplify the implementation, this is merging of multiple
        # empty lines into one. Rendering of nodes than does not have
        # to worry about an empty line already being on the stack.
        if self._rendered_paragraphs and self._rendered_paragraphs[-1] != NL:
            self._emit_paragraphs([NL])

    # Simple logging for nodes that have no effect
    def _noop_visit(self, node: docutils.nodes.Node) -> None:
        self.log_visit(node)

    def _noop_departure(self, node: docutils.nodes.Node) -> None:
        self.log_departure(node)

    # Node renderers
    visit_document = _noop_visit

    def depart_document(self, node: docutils.nodes.document) -> None:
        self.log_departure(node)

        self.flush()

    visit_section = _noop_visit
    depart_section = _noop_departure

    def visit_title(self, node: docutils.nodes.title) -> None:
        self.log_visit(node)

        self._emit('--- ' + node.astext() + ' ---')
        self.flush()

        self.nl()

        raise docutils.nodes.SkipChildren

    depart_title = _noop_departure

    def visit_paragraph(self, node: docutils.nodes.paragraph) -> None:
        self.log_visit(node)

        if isinstance(node.parent, docutils.nodes.list_item):
            if self._text_prefix:
                self._emit(self._text_prefix)
                self._text_prefix = None

            else:
                self._emit(' ' * self._indent)

    def depart_paragraph(self, node: docutils.nodes.paragraph) -> None:
        self.log_departure(node)

        self.flush()
        self.nl()

    def visit_Text(self, node: docutils.nodes.Text) -> None:  # noqa: N802
        self.log_visit(node)

        if isinstance(node.parent, docutils.nodes.literal):
            return

        self._emit(self._style_stack[-1].apply(node.astext().replace('\n', ' ')))

    depart_Text = _noop_departure  # noqa: N815

    def visit_literal(self, node: docutils.nodes.literal) -> None:
        self.log_visit(node)

        self._emit(self._theme.restructuredtext_literal.apply(node.astext()))

    depart_literal = _noop_departure

    def visit_emphasis(self, node: docutils.nodes.emphasis) -> None:
        self.log_visit(node)

        self._emit(self._theme.restructuredtext_emphasis.apply(node.astext()))

        raise docutils.nodes.SkipChildren

    depart_emphasis = _noop_departure

    def visit_strong(self, node: docutils.nodes.strong) -> None:
        self.log_visit(node)

        self._emit(self._theme.restructuredtext_strong.apply(node.astext()))

        raise docutils.nodes.SkipChildren

    depart_strong = _noop_departure

    def visit_literal_block(self, node: docutils.nodes.literal_block) -> None:
        self.log_visit(node)

        self.flush()

        if 'yaml' in node.attributes['classes']:
            style = self._theme.restructuredtext_literalblock_yaml

        elif 'shell' in node.attributes['classes']:
            style = self._theme.restructuredtext_literalblock_shell

        else:
            style = self._theme.restructuredtext_literalblock

        self._emit_paragraphs([f'    {style.apply(line)}' for line in node.astext().splitlines()])

        raise docutils.nodes.SkipChildren

    def depart_literal_block(self, node: docutils.nodes.literal_block) -> None:
        self.log_departure(node)

        self.nl()

    def visit_bullet_list(self, node: docutils.nodes.bullet_list) -> None:
        self.log_visit(node)

        self.nl()

    def depart_bullet_list(self, node: docutils.nodes.bullet_list) -> None:
        self.log_departure(node)

        self.nl()

    def visit_list_item(self, node: docutils.nodes.list_item) -> None:
        self.log_visit(node)

        self._text_prefix = self._style_stack[-1].apply('* ')
        self._indent += 2

    def depart_list_item(self, node: docutils.nodes.list_item) -> None:
        self.log_departure(node)

        self._indent -= 2

    visit_inline = _noop_visit
    depart_inline = _noop_departure

    visit_reference = _noop_visit
    depart_reference = _noop_departure

    def _visit_admonition(self, node: docutils.nodes.Admonition, header: str) -> None:
        self.log_visit(node)

        self._emit(self._style_stack[-1].apply(header))
        self.flush()

        self.nl()

    def _depart_admonition(self, node: docutils.nodes.Admonition, footer: str) -> None:
        self.log_departure(node)

        self._emit(self._style_stack[-1].apply(footer))
        self.flush()

        self.nl()

    def visit_note(self, node: docutils.nodes.note) -> None:
        self._style_stack.append(self._theme.restructuredtext_admonition_note)

        self._visit_admonition(node, NOTE_HEADER)

    def depart_note(self, node: docutils.nodes.note) -> None:
        self._depart_admonition(node, NOTE_FOOTER)

        self._style_stack.pop(-1)

    def visit_warning(self, node: docutils.nodes.warning) -> None:
        self._style_stack.append(self._theme.restructuredtext_admonition_warning)

        self._visit_admonition(node, WARNING_HEADER)

    def depart_warning(self, node: docutils.nodes.warning) -> None:
        self._depart_admonition(node, WARNING_FOOTER)

        self._style_stack.pop(-1)

    def visit_transition(self, node: docutils.nodes.transition) -> None:
        self.log_visit(node)

        self._emit(BREAK)
        self.flush()
        self.nl()

    depart_transition = _noop_departure

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
    content: Optional[Sequence[str]] = None,
) -> tuple[Sequence[docutils.nodes.reference], Sequence[docutils.nodes.reference]]:
    """
    A handler for ``:ref:`` role.

    :returns: a simple :py:class:`docutils.nodes.Text` node with text of
        the "link": ``foo`` for both ``:ref:`foo``` and
        ``:ref:`foo</bar>```.
    """

    return ([docutils.nodes.reference(rawtext, text)], [])


def parse_rst(text: str) -> docutils.nodes.document:
    """
    Parse a ReST document into docutils tree of nodes
    """

    docutils.parsers.rst.roles.register_local_role('ref', role_ref)

    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(components=components).get_default_values()
    document = docutils.utils.new_document('<rst-doc>', settings=settings)

    parser.parse(text, document)

    return document


def render_rst(text: str, logger: Logger) -> str:
    """
    Render a ReST document
    """

    logger.debug('text', text, level=4, topic=tmt.log.Topic.HELP_RENDERING)

    document = parse_rst(text)
    visitor = RestVisitor(document, logger)

    document.walkabout(visitor)

    return visitor.rendered
