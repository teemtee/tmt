"""
Metadata export functionality core.

Internal APIs, plugin classes and shared functionality and helpers for metadata
export of tests, plans or stories.
"""

import abc
import re
import traceback
import types
import xmlrpc.client
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Generic,
    Optional,
    Protocol,
    TypeVar,
    Union,
    cast,
)

import fmf
import fmf.utils
from click import echo

import tmt as tmt
import tmt.log
import tmt.utils
from tmt._compat.typing import Self
from tmt.container import container, simple_field
from tmt.plugins import PluginRegistry
from tmt.utils import Path
from tmt.utils.themes import style

if TYPE_CHECKING:
    import tmt.base

TEMPLATES_RESOURCE = 'export/templates'

bugzilla: Optional[types.ModuleType] = None

# Until Bugzilla gets its own annotations and recognizable imports...
BugzillaInstance = Any


# TODO: why this exists?
log = fmf.utils.Logging('tmt').logger


# For linking bugs
BUGZILLA_XMLRPC_URL = "https://bugzilla.redhat.com/xmlrpc.cgi"
RE_BUGZILLA_URL = r'bugzilla.redhat.com/show_bug.cgi\?id=(\d+)'

# Used to extract <h1>-<h4> headings and their text from HTML
HEADING_PATTERN = re.compile(r'^(?P<title><h(?P<level>[1-4])>.+?</h\2>)$', re.MULTILINE)


# ignore[type-arg]: bound type vars cannot be generic, and it would create a loop anyway.
ExportableT = TypeVar('ExportableT', bound='Exportable')  # type: ignore[type-arg]
ExportClass = type['ExportPlugin']

_RawExportedInstance = dict[str, Any]
_RawExportedCollection = list[_RawExportedInstance]
_RawExported = Union[_RawExportedInstance, _RawExportedCollection]


# Protocols describing export methods.
class Exporter(Protocol):
    def __call__(self, collection: list[ExportableT], keys: Optional[list[str]] = None) -> str:
        pass


class Exportable(Generic[ExportableT], tmt.utils._CommonBase, abc.ABC):  # noqa: PYI059
    """
    Mixin class adding support for exportability of class instances
    """

    # Declare export plugin registry as a class variable, but do not initialize it. If initialized
    # here, the mapping would be shared by all classes, which is not a desirable attribute.
    # Instead, mapping will be created by get_export_plugin_registry() method when called for the
    # first time.
    _export_plugin_registry: ClassVar[PluginRegistry[ExportClass]]

    # Keep this method around, to correctly support Python's method resolution order.
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    # Cannot use @property as this must remain classmethod
    @classmethod
    def get_export_plugin_registry(cls) -> PluginRegistry[ExportClass]:
        """
        Return - or initialize - export plugin registry
        """

        if not hasattr(cls, '_export_plugin_registry'):
            cls._export_plugin_registry = PluginRegistry(f'export.{cls.__name__.lower()}')

        return cls._export_plugin_registry

    @classmethod
    def provides_export(cls, format: str) -> Callable[[ExportClass], ExportClass]:
        """
        A decorator for registering export format.

        Decorate an export plugin class to register a format.
        """

        def _provides_export(export_cls: ExportClass) -> ExportClass:
            cls.get_export_plugin_registry().register_plugin(
                plugin_id=format,
                plugin=export_cls,
                logger=tmt.log.Logger.get_bootstrap_logger(),
            )

            return export_cls

        return _provides_export

    @classmethod
    def _get_exporter(cls, format: str) -> Exporter:
        """
        Find an exporter for a given format.

        Exporter class must be registered first, i.e. the plugin providing
        the format must have used :py:meth:`Exportable.provides_export`
        of this class as a class decorator.

        :param format: export format to look for.
        :returns: an :py:class:`Exporter`-like class implementing the export.
        :raises GeneralError: when there is no plugin registered for the given
            format.
        """

        exporter_class = cls.get_export_plugin_registry().get_plugin(format)

        if exporter_class is None:
            raise tmt.utils.GeneralError(
                f"Export format '{format}' not supported for {cls.__name__.lower()}."
            )

        return cast(Exporter, getattr(exporter_class, f'export_{cls.__name__.lower()}_collection'))

    @abc.abstractmethod
    def _export(self, *, keys: Optional[list[str]] = None) -> _RawExportedInstance:
        """
        Export instance as "raw" dictionary.

        The return value is often used by more advanced export methods as their starting
        position.
        """

        raise NotImplementedError

    def export(self, *, format: str, keys: Optional[list[str]] = None, **kwargs: Any) -> str:
        """
        Export this instance in a given format
        """

        return self.export_collection(
            # TODO: adding cast to make mypy happy, it seems to be puzzled by the
            # use of the generic type as a base class for this class. I suppose
            # it's right, but I have no idea what's the actual problem here. In
            # any case, `self` is definitely `ExportableT`.
            collection=[cast(ExportableT, self)],
            format=format,
            keys=keys,
            **kwargs,
        )

    @classmethod
    def export_collection(
        cls,
        *,
        collection: list[Self],
        format: str,
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Export collection of instances in a given format
        """

        exporter = cls._get_exporter(format)

        try:
            return exporter(collection, keys=keys, **kwargs)

        except NotImplementedError as error:
            raise tmt.utils.GeneralError(
                f"Export format '{format}' not supported for {cls.__name__.lower()} collection."
            ) from error


class ExportPlugin(abc.ABC):
    """
    Base class for plugins providing metadata export functionality
    """

    @classmethod
    @abc.abstractmethod
    def export_fmfid_collection(cls, fmf_ids: list['tmt.base.FmfId'], **kwargs: Any) -> str:
        """
        Export collection of fmf ids
        """

        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def export_test_collection(
        cls,
        tests: list['tmt.base.Test'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Export collection of tests
        """

        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def export_plan_collection(
        cls,
        plans: list['tmt.base.Plan'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Export collection of plans
        """

        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def export_story_collection(
        cls,
        stories: list['tmt.base.Story'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """
        Export collection of stories
        """

        raise NotImplementedError


# It's tempting to make this the default implementation of `ExporterPlugin` class,
# but that would mean the `ExportPlugin` would suddenly not raise `NotImplementedError`
# in methods where the export is not supported by a child class. That does not
# feel right, therefore the "simple export plugin" class of plugins has its own
# dedicated base.


class TrivialExporter(ExportPlugin):
    """
    A helper base class for exporters with trivial export procedure.

    Child classes need to implement a single method that performs a conversion
    of a single collection item, and that's all. It is good enough for formats
    like ``dict`` or ``YAML`` as they do not require any other input than the
    data to convert.
    """

    @classmethod
    @abc.abstractmethod
    def _export(cls, data: _RawExported) -> str:
        """
        Perform the actual conversion of internal data package to desired format.

        The method is left for child classes to implement, all other public
        methods call this method to perform the conversion for each collection
        item.

        :param data: data package to export.
        :returns: string representation of the given data.
        """

        raise NotImplementedError

    @classmethod
    def export_fmfid_collection(
        cls,
        fmf_ids: list['tmt.base.FmfId'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        # Special case: fmf id export shall not display `ref` if it is equal
        # to the default branch.
        exported_fmf_ids: list[tmt.base._RawFmfId] = []

        for fmf_id in fmf_ids:
            exported = fmf_id._export(keys=keys)

            if fmf_id.default_branch and fmf_id.ref == fmf_id.default_branch:
                exported.pop('ref')

            exported_fmf_ids.append(cast(tmt.base._RawFmfId, exported))

        return cls._export(cast(list[_RawExportedInstance], exported_fmf_ids))

    @classmethod
    def export_test_collection(
        cls,
        tests: list['tmt.base.Test'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        return cls._export([test._export(keys=keys) for test in tests])

    @classmethod
    def export_plan_collection(
        cls,
        plans: list['tmt.base.Plan'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        return cls._export([plan._export(keys=keys) for plan in plans])

    @classmethod
    def export_story_collection(
        cls,
        stories: list['tmt.base.Story'],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        return cls._export([story._export(keys=keys) for story in stories])


@container
class TestSection:
    """
    A container for test section data
    """

    name: str
    steps: list[str] = simple_field(default_factory=list)
    expects: list[str] = simple_field(default_factory=list)


@container
class MarkdownFileSection:
    """
    A container for all sections in a markdown file
    """

    tests: list[TestSection] = simple_field(default_factory=list)
    setup: list[str] = simple_field(default_factory=list)
    cleanup: list[str] = simple_field(default_factory=list)


def get_bz_instance() -> BugzillaInstance:
    """
    Import the bugzilla module and return BZ instance
    """

    try:
        import bugzilla
    except ImportError as error:
        raise tmt.utils.ConvertError(
            "Install 'tmt+test-convert' to link test to the bugzilla."
        ) from error

    try:
        bz_instance: BugzillaInstance = bugzilla.Bugzilla(url=BUGZILLA_XMLRPC_URL)
    except Exception as exc:
        log.debug(traceback.format_exc())
        raise tmt.utils.ConvertError("Couldn't initialize the Bugzilla client.") from exc

    if not bz_instance.logged_in:
        raise tmt.utils.ConvertError(
            "Not logged to Bugzilla, check 'man bugzilla' section "
            "'AUTHENTICATION CACHE AND API KEYS'."
        )
    return bz_instance


def bz_set_coverage(bug_ids: list[int], case_id: str, tracker_id: int) -> None:
    """
    Set coverage in Bugzilla
    """

    bz_instance = get_bz_instance()

    overall_pass = True
    no_email = 1  # Do not send emails about the change
    get_bz_dict = {
        'ids': bug_ids,
        'include_fields': ['id', 'external_bugs', 'flags'],
    }
    bugs_data = bz_instance._proxy.Bug.get(get_bz_dict)
    for bug in bugs_data['bugs']:
        # Process flag (might fail for some types)
        bug_id = bug['id']
        if 'qe_test_coverage+' not in {x['name'] + x['status'] for x in bug['flags']}:
            try:
                bz_instance._proxy.Flag.update(
                    {
                        'ids': [bug_id],
                        'nomail': no_email,
                        'updates': [{'name': 'qe_test_coverage', 'status': '+'}],
                    }
                )
            except xmlrpc.client.Fault as err:
                # TODO: Fix missing overall_result = False, breaks tests
                # if bug used for testing is not changed
                # BZ#1925518 can't have qe_test_coverage flag
                log.debug(f"Update flag failed: {err}")
                echo(style(f"Failed to set qe_test_coverage+ flag for BZ#{bug_id}", fg='red'))
        # Process external tracker - should succeed
        current = {
            b['ext_bz_bug_id'] for b in bug['external_bugs'] if b['ext_bz_id'] == tracker_id
        }
        if case_id not in current:
            query = {
                'bug_ids': [bug_id],
                'nomail': no_email,
                'external_bugs': [
                    {
                        'ext_type_id': tracker_id,
                        'ext_bz_bug_id': case_id,
                        'ext_description': '',
                    }
                ],
            }
            try:
                bz_instance._proxy.ExternalBugs.add_external_bug(query)
            except Exception as err:
                log.debug(f"Link case failed: {err}")
                echo(style(f"Failed to link to BZ#{bug_id}", fg='red'))
                overall_pass = False
    if not overall_pass:
        raise tmt.utils.ConvertError("Failed to link the case to bugs.")

    echo(
        style(
            "Linked to Bugzilla: {}.".format(" ".join([f"BZ#{bz_id}" for bz_id in bug_ids])),
            fg='magenta',
        )
    )


def check_md_file_respects_spec(md_path: Path) -> list[str]:
    """
    Check that the file respects manual test specification

    Return list of warnings, empty list if no problems found.
    """

    import tmt.base

    def get_heading_section(heading: str) -> Optional[str]:
        """Determine the section type for a heading."""
        for section, patterns in tmt.base.SECTIONS_HEADINGS.items():
            for pattern in patterns:
                if pattern.match(heading):
                    return section
        return None

    # Extract headings
    md_to_html = tmt.utils.markdown_to_html(md_path)
    headings = [
        (int(match.group('level')), match.group('title'))
        for match in HEADING_PATTERN.finditer(md_to_html)
    ]
    warnings = []
    file_section = MarkdownFileSection()
    current_test: Optional[TestSection] = None

    for level, heading in headings:
        section_type = get_heading_section(heading)

        # Ignore unknown headings
        if not section_type:
            warnings.append(f'unknown html heading "{heading}" is used')

        # Collect Setup/Cleanup occurrences
        if section_type == "Setup":
            file_section.setup.append(heading)
        elif section_type == "Cleanup":
            file_section.cleanup.append(heading)

        # Start new test section on h1 heading
        if level == 1:
            current_test = TestSection(name=heading) if section_type == "Test" else None
            if current_test:
                file_section.tests.append(current_test)
            continue

        # Inside an open test section
        if current_test:
            if section_type == "Step":
                current_test.steps.append(heading)
            elif section_type == "Expect":
                current_test.expects.append(heading)
            else:
                warnings.append(
                    f'Heading "{heading}" isn\'t expected in the section "{current_test.name}"'
                )
        # Outside test section — detect orphan Step/Expect
        elif section_type in {"Step", "Expect"}:
            warnings.append(
                f'Heading "{heading}" from the section "{section_type}" is '
                f'used outside of Test sections.'
            )

    # Warn if more than one Setup or Cleanup
    warnings.extend(
        f'{len(h)} headings "{h[0]}" are used'
        for h in (file_section.setup, file_section.cleanup)
        if len(h) > 1
    )

    # At least one test section must exist
    if not file_section.tests:
        warnings.append('"Test" section doesn\'t exist in the Markdown file')
        return warnings

    # # Step isn't in pair with # Expect
    for test in file_section.tests:
        steps_count = len(test.steps)
        expects_count = len(test.expects)
        if steps_count != expects_count:
            warnings.append(
                f'The number of headings from the section "Step" - {steps_count}'
                f' doesn\'t equal to the number of headings from the section'
                f' "Expect" - {expects_count} in the test section "{test.name}"'
            )

    return warnings
