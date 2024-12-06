import re
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any, Optional, Union

import fmf.utils

from tmt.utils import StructuredFieldError, format_value, pure_ascii

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  StructuredField
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

log = fmf.utils.Logging('tmt').logger

SFSectionValueType = Union[str, list[str]]


class StructuredField:
    """
    Handling multiple text data in a single text field

    The StructuredField allows you to easily store and extract several
    sections of text data to/from a single text field. The sections are
    separated by section names in square brackets and can be hosted in
    other text as well.

    The section names have to be provided on a separate line and there
    must be no leading/trailing white space before/after the brackets.
    The StructuredField supports two versions of the format:

    Version 0: Simple, concise, useful when neither the surrounding text
    or the section data can contain lines which could resemble section
    names. Here's an example of a simple StructuredField:

    .. code-block:: ini

        Note written by human.

        [section-one]
        Section one content.

        [section-two]
        Section two content.

        [section-three]
        Section three content.

        [end]

        Another note written by human.

    Version 1: Includes unique header to prevent collisions with the
    surrounding text and escapes any section-like lines in the content:

    .. code-block:: ini

        Note written by human.

        [structured-field-start]
        This is StructuredField version 1. Please, edit with care.

        [section-one]
        Section one content.

        [section-two]
        Section two content.
        [structured-field-escape][something-resembling-section-name]

        [section-three]
        Section three content.

        [structured-field-end]

        Another note written by human.

    Note that an additional empty line is added at the end of each
    section to improve the readability. This line is not considered
    to be part of the section content.

    Besides handling the whole section content it's also possible to
    store several key-value pairs in a single section, similarly as in
    the ini config format:

    .. code-block:: ini

        [section]
        key1 = value1
        key2 = value2
        key3 = value3

    Provide the key name as the optional argument 'item' when accessing
    these single-line items. Note that the section cannot contain both
    plain text data and key-value pairs.

    .. code-block:: python

        field = qe.StructuredField()
        field.set("project", "Project Name")
        field.set("details", "somebody", "owner")
        field.set("details", "2013-05-27", "started")
        field.set("description", "This is a description.\\n"
                "It spans across multiple lines.\\n")
        print field.save()

            [structured-field-start]
            This is StructuredField version 1. Please, edit with care.

            [project]
            Project Name

            [details]
            owner = somebody
            started = 2013-05-27

            [description]
            This is a description.
            It spans across multiple lines.

            [structured-field-end]

        field.version(0)
        print field.save()

            [project]
            Project Name

            [details]
            owner = somebody
            started = 2013-05-27

            [description]
            This is a description.
            It spans across multiple lines.

            [end]

    Multiple values for the same key are supported as well. Enable this
    feature with 'multi=True' when initializing the structured field.
    If multiple values are present their list will be returned instead
    of a single string. Similarly use list for setting multiple values:

    .. code-block:: python

        field = qe.StructuredField(multi=True)
        requirements = ['hypervisor=', 'labcontroller=lab.example.com']
        field.set("hardware", requirements, "hostrequire")
        print field.save()

            [structured-field-start]
            This is StructuredField version 1. Please, edit with care.

            [hardware]
            hostrequire = hypervisor=
            hostrequire = labcontroller=lab.example.com

            [structured-field-end]

        print field.get("hardware", "hostrequire")

            ['hypervisor=', 'labcontroller=lab.example.com']

    """

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Special
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def __init__(
            self,
            text: Optional[str] = None,
            version: int = 1,
            multi: bool = False) -> None:
        """ Initialize the structured field """
        self.version(version)
        self._header: str = ""
        self._footer: str = ""
        # Sections are internally stored in their serialized form, i.e. as
        # strings.
        self._sections: dict[str, str] = {}
        self._order: list[str] = []
        self._multi = multi
        if text is not None:
            self.load(text)

    def __iter__(self) -> Iterator[str]:
        """ By default iterate through all available section names """
        yield from self._order

    def __nonzero__(self) -> bool:
        """ True when any section is defined """
        return len(self._order) > 0

    __bool__ = __nonzero__

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Private
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _load_version_zero(self, text: str) -> None:
        """ Load version 0 format """
        # Attempt to split the text according to the section tag
        section = re.compile(r"\n?^\[([^\]]+)\]\n", re.MULTILINE)
        parts = section.split(text)
        # If just one part ---> no sections present, just plain text
        if len(parts) == 1:
            self._header = parts[0]
            return
        # Pick header & footer, make sure [end] tag is present
        self._header = parts[0]
        self._footer = re.sub("^\n", "", parts[-1])
        if parts[-2] != "end":
            raise StructuredFieldError("No [end] section tag found")
        # Convert to dictionary and save the order
        keys = parts[1:-2:2]
        values = parts[2:-2:2]
        for key, value in zip(keys, values):
            self.set(key, value)

    def _load(self, text: str) -> None:
        """ Load version 1+ format """
        # The text must exactly match the format
        format = re.compile(
            r"(.*)^\[structured-field-start\][ \t]*\n"
            r"(.*)\n\[structured-field-end\][ \t]*\n(.*)",
            re.DOTALL + re.MULTILINE)
        # No match ---> plain text or broken structured field
        matched = format.search(text)
        if not matched:
            if "[structured-field" in text:
                raise StructuredFieldError("StructuredField parse error")
            self._header = text
            log.debug("StructuredField not found, treating as a plain text")
            return
        # Save header & footer (remove trailing new lines)
        self._header = re.sub("\n\n$", "\n", matched.groups()[0])
        if self._header:
            log.debug(f"Parsed header:\n{self._header}")
        self._footer = re.sub("^\n", "", matched.groups()[2])
        if self._footer:
            log.debug(f"Parsed footer:\n{self._footer}")
        # Split the content on the section names
        section = re.compile(r"\n\[([^\]]+)\][ \t]*\n", re.MULTILINE)
        parts = section.split(matched.groups()[1])
        # Detect the version
        version_match = re.search(r"version (\d+)", parts[0])
        if not version_match:
            log.error(parts[0])
            raise StructuredFieldError(
                "Unable to detect StructuredField version")
        self.version(int(version_match.groups()[0]))
        log.debug(
            f"Detected StructuredField version {self.version()}")
        # Convert to dictionary, remove escapes and save the order
        keys = parts[1::2]
        escape = re.compile(r"^\[structured-field-escape\]", re.MULTILINE)
        values = [escape.sub("", value) for value in parts[2::2]]
        for key, value in zip(keys, values):
            self.set(key, value)
        log.debug(f"Parsed sections:\n{format_value(self._sections)}")

    def _save_version_zero(self) -> str:
        """ Save version 0 format """
        result = []
        if self._header:
            result.append(self._header)
        for section, content in self.iterate():
            result.append(f"[{section}]\n{content}")
        if self:
            result.append("[end]\n")
        if self._footer:
            result.append(self._footer)
        return "\n".join(result)

    def _save(self) -> str:
        """ Save version 1+ format """
        result = []
        # Regular expression for escaping section-like lines
        escape = re.compile(r"^(\[.+\])$", re.MULTILINE)
        # Header
        if self._header:
            result.append(self._header)
        # Sections
        if self:
            result.append(
                "[structured-field-start]\n"
                f"This is StructuredField version {self._version}. "
                "Please, edit with care.\n")
            for section, content in self.iterate():
                result.append("[{}]\n{}".format(section, escape.sub(
                    "[structured-field-escape]\\1", content)))
            result.append("[structured-field-end]\n")
        # Footer
        if self._footer:
            result.append(self._footer)
        return "\n".join(result)

    def _read_section(self, content: str) -> dict[str, SFSectionValueType]:
        """ Parse config section and return ordered dictionary """
        dictionary: dict[str, SFSectionValueType] = OrderedDict()
        for line in content.split("\n"):
            # Remove comments and skip empty lines
            line = re.sub("#.*", "", line)
            if re.match(r"^\s*$", line):
                continue
            # Parse key and value
            matched = re.search("([^=]+)=(.*)", line)
            if not matched:
                raise StructuredFieldError(
                    f"Invalid key/value line: {line}")
            key = matched.groups()[0].strip()
            value = matched.groups()[1].strip()
            # Handle multiple values if enabled
            if key in dictionary and self._multi:
                stored_value = dictionary[key]
                if isinstance(stored_value, list):
                    stored_value.append(value)
                else:
                    dictionary[key] = [stored_value, value]
            else:
                dictionary[key] = value
        return dictionary

    def _write_section(self, dictionary: dict[str, SFSectionValueType]) -> str:
        """ Convert dictionary into a config section format """
        section = ""
        for key, value in dictionary.items():
            if isinstance(value, list):
                for item in value:
                    section += f"{key} = {item}\n"
            else:
                section += f"{key} = {value}\n"
        return section

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Methods
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def iterate(self) -> Iterator[tuple[str, str]]:
        """ Return (section, content) tuples for all sections """
        for section in self:
            yield section, self._sections[section]

    def version(self, version: Optional[int] = None) -> int:
        """ Get or set the StructuredField version """
        if version is not None:
            if version in [0, 1]:
                self._version = version
            else:
                raise StructuredFieldError(
                    f"Bad StructuredField version: {version}")
        return self._version

    def load(self, text: str, version: Optional[int] = None) -> None:
        """ Load the StructuredField from a string """
        if version is not None:
            self.version(version)
        # Make sure we got a text, convert from bytes if necessary
        if isinstance(text, bytes):
            text = text.decode("utf8")
        if not isinstance(text, str):
            raise StructuredFieldError(
                "Invalid StructuredField, expecting string")
        # Remove possible carriage returns
        text = re.sub("\r\n", "\n", text)
        # Make sure the text has a new line at the end
        if text and text[-1] != "\n":
            text += "\n"
        log.debug(f"Parsing StructuredField\n{text}")
        # Parse respective format version
        if self._version == 0:
            self._load_version_zero(text)
        else:
            self._load(text)

    def save(self) -> str:
        """ Convert the StructuredField into a string """
        if self.version() == 0:
            return self._save_version_zero()
        return self._save()

    def header(self, content: Optional[str] = None) -> str:
        """ Get or set the header content """
        if content is not None:
            self._header = content
        return self._header

    def footer(self, content: Optional[str] = None) -> str:
        """ Get or set the footer content """
        if content is not None:
            self._footer = content
        return self._footer

    def sections(self) -> list[str]:
        """ Get the list of available sections """
        return self._order

    def get(
            self,
            section: str,
            item: Optional[str] = None) -> SFSectionValueType:
        """ Return content of given section or section item """
        try:
            content = self._sections[section]
        except KeyError:
            raise StructuredFieldError(
                f"Section [{pure_ascii(section)!r}] not found")
        # Return the whole section content
        if item is None:
            return content
        # Return only selected item from the section
        try:
            return self._read_section(content)[item]
        except KeyError:
            raise StructuredFieldError(
                f"Unable to read '{pure_ascii(item)!r}' from section '{pure_ascii(section)!r}'")

    def set(self, section: str, content: Any,
            item: Optional[str] = None) -> None:
        """ Update content of given section or section item """
        # Convert to string if necessary, keep lists untouched
        if isinstance(content, list):
            pass
        elif isinstance(content, bytes):
            content = content.decode("utf8")
        elif not isinstance(content, str):
            content = str(content)
        # Set the whole section content
        if item is None:
            # Add new line if missing
            if content and content[-1] != "\n":
                content += "\n"
            self._sections[section] = content
        # Set only selected item from the section
        else:
            try:
                current = self._sections[section]
            except KeyError:
                current = ""
            dictionary = self._read_section(current)
            dictionary[item] = content
            self._sections[section] = self._write_section(dictionary)
        # Remember the order when adding a new section
        if section not in self._order:
            self._order.append(section)

    def remove(self, section: str, item: Optional[str] = None) -> None:
        """ Remove given section or section item """
        # Remove the whole section
        if item is None:
            try:
                del self._sections[section]
                del self._order[self._order.index(section)]
            except KeyError:
                raise StructuredFieldError(
                    f"Section [{pure_ascii(section)!r}] not found")
        # Remove only selected item from the section
        else:
            try:
                dictionary = self._read_section(self._sections[section])
                del (dictionary[item])
            except KeyError:
                raise StructuredFieldError(
                    f"Unable to remove '{pure_ascii(item)!r}' "
                    f"from section '{pure_ascii(section)!r}'"
                    )
            self._sections[section] = self._write_section(dictionary)
