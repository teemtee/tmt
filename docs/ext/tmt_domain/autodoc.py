import abc
import copy
import itertools
import typing
from contextlib import contextmanager
from typing import Optional, overload

from docutils.statemachine import StringList
from sphinx.util.docutils import SphinxDirective, switch_source_input

if typing.TYPE_CHECKING:
    from collections.abc import Generator

    from docutils.nodes import Node

    from tmt._compat.typing import Self

RST_DIRECTIVE_INDENT = 3
LIST_INDENT = 2


# TODO: Support markdown format too
#  (it would be much easier since it doesn't need to handle indents)
class Content(StringList):
    """
    Wrapper around ``StringList`` with helper functions for formatting rst contents.
    """

    #: Current rst content indent of the content
    indent: int
    #: Flag that checks if we have added the relevant list symbol
    needs_list_symbol: bool
    #: How many ``list`` context are we in
    list_layer: int

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.indent = 0
        self.needs_list_symbol = False
        self.list_layer = 0

    def _indent_str(self, orig: str) -> str:
        """
        Prepend all the necessary indent and possibly the list symbol.
        """
        if self.needs_list_symbol:
            # Indent the line and add the list symbol
            self.needs_list_symbol = False
            return " " * (self.indent - 2) + "* " + orig
        if not orig.strip():
            # No need to indent if the line is empty
            return ""
        # Indented line
        return " " * self.indent + orig

    @overload
    def _indent_other(self, other: StringList) -> StringList: ...

    @overload
    def _indent_other(self, other: list[str]) -> list[str]: ...

    @overload
    def _indent_other(self, other: str) -> str: ...

    def _indent_other(self, other):
        """
        Main helper function to indent any operand that is using
        """
        # TODO: Do we need to copy the other?
        if isinstance(other, StringList):
            other = copy.deepcopy(other)
            other.data = [self._indent_str(line) for line in other.data]
            return other
        if isinstance(other, list):
            return [self._indent_str(line) for line in other]
        if isinstance(other, str):
            return self._indent_str(other)
        raise NotImplementedError(f"Trying to indent an unknown input type: {type(other)}")

    # We need to override any methods used to insert items
    # Also considered manipulating data instead, but the same methods
    # would have been overwritten there instead.
    def __setitem__(self, i, item):
        item = self._indent_other(item)
        super().__setitem__(i, item)

    def __add__(self, other):
        other = self._indent_other(other)
        return super().__add__(other)

    def __radd__(self, other):
        other = self._indent_other(other)
        return super().__radd__(other)

    def __iadd__(self, other):
        other = self._indent_other(other)
        return super().__iadd__(other)

    def extend(self, other):
        other = self._indent_other(other)
        super().extend(other)

    def append(self, item, source=None, offset=0):
        item = self._indent_other(item)
        super().append(item, source, offset)

    def insert(self, i, item, source=None, offset=0):
        item = self._indent_other(item)
        super().insert(i, item, source, offset)

    # Context helpers
    @contextmanager
    def directive(
        self,
        name: str,
        *directive_args: str,
        source: str,
        offset_count: Optional[itertools.count] = None,
        **directive_kwargs: Optional[str],
    ) -> "Generator[Self]":
        """
        Add the directive header and start appending its content.

        This handles the rst indentation of the directive content introduced.

        :param name: directive name
        :param directive_args: directive's parameters
        :param directive_kwargs: other directive arguments
        :param source: the source name that owns the lines written here
        :param offset_count: counter tracking the line numbers of the source
        """

        def get_offset() -> int:
            if offset_count:
                return next(offset_count)
            return 0

        # TODO: multiple signature is not supported
        # TODO: add some meaningful source like using inspect to get the caller's source
        # Add the directive header
        self.append(
            f".. {name}:: {', '.join(directive_args)}".rstrip(),
            source=source,
            offset=get_offset(),
        )
        self.indent += RST_DIRECTIVE_INDENT
        for key, value in directive_kwargs.items():
            self.append(
                f":{key}: {value or ''}".rstrip(),
                source=source,
                offset=get_offset(),
            )
        self.append(
            "",
            source=source,
            offset=get_offset(),
        )
        # Start adding other contents
        yield self
        # exit the directive
        self.append(
            "",
            source=source,
            offset=get_offset(),
        )
        self.indent -= RST_DIRECTIVE_INDENT
        assert self.indent >= 0

    @contextmanager
    def new_list(
        self,
        *,
        source: str,
        offset_count: Optional[itertools.count] = None,
    ) -> "Generator[Self]":
        """
        Start a new list context.

        Use :py:meth:`new_item` to add start a new list item.

        :param source: the source name that owns the lines written here
        :param offset_count: counter tracking the line numbers of the source
        """

        def get_offset() -> int:
            if offset_count:
                return next(offset_count)
            return 0

        self.needs_list_symbol = True
        self.list_layer += 1
        self.indent += LIST_INDENT
        yield self
        # exit the directive
        self.append("", source=source, offset=get_offset())
        self.indent -= LIST_INDENT
        self.list_layer -= 1
        assert self.list_layer >= 0
        assert self.indent >= 0

    def new_item(self) -> None:
        """
        Start adding the contents of a new item.

        Must be called within a :py:meth:`list` context.
        """
        if not self.list_layer:
            raise SyntaxError("new_item was used outside of a list context")
        self.needs_list_symbol = True


class AutodocDirectiveBase(SphinxDirective, abc.ABC):
    """
    A base class for out autodoc directives.
    """

    content: Content
    # TODO: Allow additional content
    has_content = False
    content_offset_count: itertools.count

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.content_offset_count = itertools.count()

    @abc.abstractmethod
    def _generate_autodoc_content(self) -> None:
        """
        Main method generating the actual contents.
        """
        raise NotImplementedError

    @property
    def autodoc_source(self) -> str:
        """
        The default source name reported in the generated content.
        """
        if self.arguments:
            return f"{self.name}[{self.arguments[0]}]"
        return self.name

    def new_line(self) -> None:
        """
        Wrapper around :py:meth:`Content.append` to add a single new line.

        Uses the :py:attr:`autodoc_source` as a source context.
        """
        self.content.append(
            "",
            source=self.autodoc_source,
            offset=next(self.content_offset_count),
        )

    def append(self, text: str) -> None:
        """
        Wrapper around :py:meth:`Content.append` to add a text block.

        Uses the :py:attr:`autodoc_source` as a source context.

        :param text: text to be added to the content
        """
        for line in text.splitlines():
            self.content.append(
                line,
                source=self.autodoc_source,
                offset=next(self.content_offset_count),
            )

    @contextmanager
    def directive(
        self,
        name: str,
        *directive_args: str,
        **directive_kwargs: Optional[str],
    ) -> "Generator[Content]":
        """
        Wrapper around :py:meth:`Content.directive`.

        Uses the :py:attr:`autodoc_source` as a source context.
        """
        with self.content.directive(
            name,
            *directive_args,
            source=self.autodoc_source,
            offset_count=self.content_offset_count,
            **directive_kwargs,
        ) as content:
            yield content

    @contextmanager
    def new_list(self) -> "Generator[Content]":
        """
        Wrapper around :py:meth:`Content.list`.

        Uses the :py:attr:`autodoc_source` as a source context.
        """
        with self.content.new_list(
            source=self.autodoc_source,
            offset_count=self.content_offset_count,
        ) as content:
            yield content

    def new_item(self) -> None:
        """
        Wrapper around :py:meth:`Content.new_item`.
        """
        self.content.new_item()

    def run(self) -> list["Node"]:
        self.content = Content()
        self._generate_autodoc_content()
        # TODO: docutils reporter does not take the sources from the content?
        with switch_source_input(self.state, self.content):
            return self.parse_content_to_nodes(allow_section_headings=True)
