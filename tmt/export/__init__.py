"""
Metadata export functionality core.

Internal APIs, plugin classes and shared functionality and helpers for metadata
export of tests, plans or stories.
"""

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
from click import echo, style

import tmt
import tmt.log
import tmt.utils
from tmt.plugins import PluginRegistry
from tmt.utils import Path

if TYPE_CHECKING:
    import tmt.base

TEMPLATES_DIRECTORY = tmt.utils.resource_files('export/templates')

bugzilla: Optional[types.ModuleType] = None

# Until Bugzilla gets its own annotations and recognizable imports...
BugzillaInstance = Any


# TODO: why this exists?
log = fmf.utils.Logging('tmt').logger


# For linking bugs
BUGZILLA_XMLRPC_URL = "https://bugzilla.redhat.com/xmlrpc.cgi"
RE_BUGZILLA_URL = r'bugzilla.redhat.com/show_bug.cgi\?id=(\d+)'


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


class Exportable(Generic[ExportableT], tmt.utils._CommonBase):
    """ Mixin class adding support for exportability of class instances """

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
        """ Return - or initialize - export plugin registry """

        if not hasattr(cls, '_export_plugin_registry'):
            cls._export_plugin_registry = PluginRegistry()

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
                logger=tmt.log.Logger.get_bootstrap_logger())

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
                f"Export format '{format}' not supported for {cls.__name__.lower()}.")

        return cast(Exporter, getattr(
            exporter_class, f'export_{cls.__name__.lower()}_collection'))

    def _export(self, *, keys: Optional[list[str]] = None) -> _RawExportedInstance:
        """
        Export instance as "raw" dictionary.

        The return value is often used by more advanced export methods as their starting
        position.
        """

        raise NotImplementedError

    def export(self, *, format: str, keys: Optional[list[str]] = None, **kwargs: Any) -> str:
        """ Export this instance in a given format """

        return self.export_collection(
            # TODO: adding cast to make mypy happy, it seems to be puzzled by the
            # use of the generic type as a base class for this class. I suppose
            # it's right, but I have no idea what's the actual problem here. In
            # any case, `self` is definitely `ExportableT`.
            collection=[cast(ExportableT, self)],
            format=format,
            keys=keys,
            **kwargs)

    @classmethod
    def export_collection(
            cls: type[ExportableT],
            *,
            collection: list[ExportableT],
            format: str,
            keys: Optional[list[str]] = None,
            **kwargs: Any) -> str:
        """ Export collection of instances in a given format """

        exporter = cls._get_exporter(format)

        try:
            return exporter(collection, keys=keys, **kwargs)

        except NotImplementedError:
            raise tmt.utils.GeneralError(
                f"Export format '{format}' not supported for {cls.__name__.lower()} collection.")


class ExportPlugin:
    """ Base class for plugins providing metadata export functionality """

    @classmethod
    def export_fmfid_collection(cls, fmf_ids: list['tmt.base.FmfId'], **kwargs: Any) -> str:
        """ Export collection of fmf ids """
        raise NotImplementedError

    @classmethod
    def export_test_collection(cls,
                               tests: list['tmt.base.Test'],
                               keys: Optional[list[str]] = None,
                               **kwargs: Any) -> str:
        """ Export collection of tests """
        raise NotImplementedError

    @classmethod
    def export_plan_collection(cls,
                               plans: list['tmt.base.Plan'],
                               keys: Optional[list[str]] = None,
                               **kwargs: Any) -> str:
        """ Export collection of plans """
        raise NotImplementedError

    @classmethod
    def export_story_collection(cls,
                                stories: list['tmt.base.Story'],
                                keys: Optional[list[str]] = None,
                                **kwargs: Any) -> str:
        """ Export collection of stories """
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
    def export_fmfid_collection(cls,
                                fmf_ids: list['tmt.base.FmfId'],
                                keys: Optional[list[str]] = None,
                                **kwargs: Any) -> str:
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
    def export_test_collection(cls,
                               tests: list['tmt.base.Test'],
                               keys: Optional[list[str]] = None,
                               **kwargs: Any) -> str:
        return cls._export([test._export(keys=keys) for test in tests])

    @classmethod
    def export_plan_collection(cls,
                               plans: list['tmt.base.Plan'],
                               keys: Optional[list[str]] = None,
                               **kwargs: Any) -> str:
        return cls._export([plan._export(keys=keys) for plan in plans])

    @classmethod
    def export_story_collection(cls,
                                stories: list['tmt.base.Story'],
                                keys: Optional[list[str]] = None,
                                **kwargs: Any) -> str:
        return cls._export([story._export(keys=keys) for story in stories])


def get_bz_instance() -> BugzillaInstance:
    """ Import the bugzilla module and return BZ instance """
    try:
        import bugzilla
    except ImportError:
        raise tmt.utils.ConvertError(
            "Install 'tmt+test-convert' to link test to the bugzilla.")

    try:
        bz_instance: BugzillaInstance = bugzilla.Bugzilla(url=BUGZILLA_XMLRPC_URL)
    except Exception as exc:
        log.debug(traceback.format_exc())
        raise tmt.utils.ConvertError("Couldn't initialize the Bugzilla client.") from exc

    if not bz_instance.logged_in:
        raise tmt.utils.ConvertError(
            "Not logged to Bugzilla, check 'man bugzilla' section "
            "'AUTHENTICATION CACHE AND API KEYS'.")
    return bz_instance


def bz_set_coverage(bug_ids: list[int], case_id: str, tracker_id: int) -> None:
    """ Set coverage in Bugzilla """
    bz_instance = get_bz_instance()

    overall_pass = True
    no_email = 1  # Do not send emails about the change
    get_bz_dict = {
        'ids': bug_ids,
        'include_fields': ['id', 'external_bugs', 'flags']}
    bugs_data = bz_instance._proxy.Bug.get(get_bz_dict)
    for bug in bugs_data['bugs']:
        # Process flag (might fail for some types)
        bug_id = bug['id']
        if 'qe_test_coverage+' not in {
                x['name'] + x['status'] for x in bug['flags']}:
            try:
                bz_instance._proxy.Flag.update({
                    'ids': [bug_id],
                    'nomail': no_email,
                    'updates': [{
                        'name': 'qe_test_coverage',
                        'status': '+'
                        }]
                    })
            except xmlrpc.client.Fault as err:
                # TODO: Fix missing overall_result = False, breaks tests
                # if bug used for testing is not changed
                # BZ#1925518 can't have qe_test_coverage flag
                log.debug(f"Update flag failed: {err}")
                echo(style(
                    f"Failed to set qe_test_coverage+ flag for BZ#{bug_id}",
                    fg='red'))
        # Process external tracker - should succeed
        current = {
            b['ext_bz_bug_id'] for b in bug['external_bugs']
            if b['ext_bz_id'] == tracker_id}
        if case_id not in current:
            query = {
                'bug_ids': [bug_id],
                'nomail': no_email,
                'external_bugs': [{
                    'ext_type_id': tracker_id,
                    'ext_bz_bug_id': case_id,
                    'ext_description': '',
                    }]
                }
            try:
                bz_instance._proxy.ExternalBugs.add_external_bug(query)
            except Exception as err:
                log.debug(f"Link case failed: {err}")
                echo(style(f"Failed to link to BZ#{bug_id}", fg='red'))
                overall_pass = False
    if not overall_pass:
        raise tmt.utils.ConvertError("Failed to link the case to bugs.")

    echo(style("Linked to Bugzilla: {}.".format(
        " ".join([f"BZ#{bz_id}" for bz_id in bug_ids])), fg='magenta'))


def check_md_file_respects_spec(md_path: Path) -> list[str]:
    """
    Check that the file respects manual test specification

    Return list of warnings, empty list if no problems found.
    """
    import tmt.base
    warnings_list = []
    sections_headings = tmt.base.SECTIONS_HEADINGS
    required_headings = set(sections_headings['Step'] +
                            sections_headings['Expect'])
    values = []
    for _ in list(sections_headings.values()):
        values += _

    md_to_html = tmt.utils.markdown_to_html(md_path)
    html_headings_from_file = [i[0] for i in
                               re.findall('(^<h[1-4]>(.+?)</h[1-4]>$)',
                                          md_to_html,
                                          re.M)]

    # No invalid headings in the file w/o headings
    if not html_headings_from_file:
        invalid_headings = []
    else:
        # Find invalid headings in the file
        invalid_headings = [key for key in set(html_headings_from_file)
                            if (key not in values) !=
                            bool(re.search(
                                sections_headings['Test'][1], key))]

    # Remove invalid headings from html_headings_from_file
    for index in invalid_headings:
        warnings_list.append(f'unknown html heading "{index}" is used')
        html_headings_from_file = [i for i in html_headings_from_file
                                   if i != index]

    def count_html_headings(heading: str) -> None:
        if html_headings_from_file.count(heading) > 1:
            warnings_list.append(
                f'{html_headings_from_file.count(heading)}'
                f' headings "{heading}" are used')

    # Warn if 2 or more # Setup or # Cleanup are used
    count_html_headings(sections_headings['Setup'][0])
    count_html_headings(sections_headings['Cleanup'][0])

    warn_outside_test_section = 'Heading "{}" from the section "{}" is '\
                                'used \noutside of Test sections.'
    warn_headings_not_in_pairs = 'The number of headings from the section' \
                                 ' "Step" - {}\ndoesn\'t equal to the ' \
                                 'number of headings from the section \n' \
                                 '"Expect" - {} in the test section "{}"'
    warn_required_section_is_absent = '"{}" section doesn\'t exist in ' \
                                      'the Markdown file'
    warn_unexpected_headings = 'Headings "{}" aren\'t expected in the ' \
                               'section "{}"'

    def required_section_exists(
            section: list[str],
            section_name: str,
            prefix: Union[str, tuple[str, ...]]) -> int:
        res = list(filter(
            lambda t: t.startswith(prefix), section))
        if not res:
            warnings_list.append(
                warn_required_section_is_absent.format(section_name))
            return 0
        return len(res)

    # Required sections don't exist
    if not required_section_exists(html_headings_from_file,
                                   'Test',
                                   '<h1>Test'):
        return warnings_list

    # Remove Optional heading #Cleanup if it's in the end of document
    if html_headings_from_file[-1] == '<h1>Cleanup</h1>':
        html_headings_from_file.pop()
        # Add # Test heading to close the file
        html_headings_from_file.append(sections_headings['Test'][0])

    index = 0
    while html_headings_from_file:
        # # Step cannot be used outside of test sections.
        if html_headings_from_file[index] == \
                sections_headings['Step'][0] or \
                html_headings_from_file[index] == \
                sections_headings['Step'][1]:
            warnings_list.append(warn_outside_test_section.format(
                html_headings_from_file[index], 'Step'))

        # # Expect cannot be used outside of test sections.
        if html_headings_from_file[index] == \
                sections_headings['Expect'][0] or \
                html_headings_from_file[index] == \
                sections_headings['Expect'][1] or \
                html_headings_from_file[index] == \
                sections_headings['Expect'][2]:
            warnings_list.append(warn_outside_test_section.format(
                html_headings_from_file[index], 'Expect'))

        if html_headings_from_file[index].startswith('<h1>Test'):
            test_section_name = html_headings_from_file[index]
            try:
                html_headings_from_file[index + 1]
            except IndexError:
                break
            for i, v in enumerate(html_headings_from_file[index + 1:]):
                if re.search('^<h1>(Test .*|Test)</h1>$', v):
                    test_section = html_headings_from_file[index + 1:
                                                           index + 1 + i]

                    # Unexpected headings inside Test section
                    unexpected_headings = set(test_section) - \
                        required_headings
                    if unexpected_headings:
                        warnings_list.append(
                            warn_unexpected_headings.
                            format(', '.join(unexpected_headings),
                                   test_section_name))

                    amount_of_steps = required_section_exists(
                        test_section,
                        'Step',
                        tuple(sections_headings['Step']))
                    amount_of_expects = required_section_exists(
                        test_section,
                        'Expect',
                        tuple(sections_headings['Expect']))

                    # # Step isn't in pair with # Expect
                    if amount_of_steps != amount_of_expects != 0:
                        warnings_list.append(warn_headings_not_in_pairs.
                                             format(amount_of_steps,
                                                    amount_of_expects,
                                                    test_section_name))
                    index += i
                    break

        index += 1
        if index >= len(html_headings_from_file) - 1:
            break
    return warnings_list
