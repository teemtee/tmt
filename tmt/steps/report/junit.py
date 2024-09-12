import dataclasses
import functools
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Optional, TypedDict, cast, overload

from jinja2 import FileSystemLoader, select_autoescape

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.result
import tmt.steps
import tmt.steps.report
import tmt.utils
from tmt.plugins import ModuleImporter
from tmt.result import ResultOutcome
from tmt.utils import Path, field
from tmt.utils.templates import default_template_environment, render_template_file

if TYPE_CHECKING:
    import lxml

    from tmt._compat.typing import TypeAlias

    XMLElement: TypeAlias = Any


DEFAULT_NAME = 'junit.xml'
DEFAULT_FLAVOR_NAME = 'default'
CUSTOM_FLAVOR_NAME = 'custom'

# Relative path to tmt junit template directory.
DEFAULT_TEMPLATE_DIR = Path('steps/report/junit/templates/')

# ignore[unused-ignore]: Pyright would report that "module cannot be
# used as a type", and it would be correct. On the other hand, it works,
# and both mypy and pyright are able to propagate the essence of a given
# module through `ModuleImporter` that, eventually, the module object
# returned by the importer does have all expected members.
#
# The error message does not have its own code, but simple `type: ignore`
# is enough to suppress it. And then mypy complains about an unused
# ignore, hence `unused-ignore` code, leading to apparently confusing
# directive.
import_lxml: ModuleImporter['lxml'] = ModuleImporter(  # type: ignore[valid-type]
    'lxml',
    tmt.utils.ReportError,
    "Missing 'lxml', fixable by 'pip install tmt[report-junit]'.",
    tmt.log.Logger.get_bootstrap_logger())


@overload
def duration_to_seconds(duration: str) -> int: pass


@overload
def duration_to_seconds(duration: None) -> None: pass


def duration_to_seconds(duration: Optional[str]) -> Optional[int]:
    """ Convert valid duration string in to seconds """
    if duration is None:
        return None
    try:
        h, m, s = duration.split(':')
        return int(h) * 3600 + int(m) * 60 + int(s)
    except Exception as error:
        raise tmt.utils.ReportError(f"Malformed duration '{duration}'.") from error


class ResultWrapper:
    """
    The context wrapper for :py:class:`tmt.Result`.

    Adds possibility to wrap the :py:class:`tmt.Result` and dynamically add more attributes which
    get available inside the template context.
    """

    class PropertyDict(TypedDict):
        """ Defines a property dict, which gets propagated into the final template properties. """

        name: str
        value: str

    def __init__(self, wrapped: tmt.Result) -> None:
        self._wrapped = wrapped
        self._properties: dict[str, str] = {}

    @property
    def properties(self) -> list[PropertyDict]:
        return [{'name': k, 'value': v} for k, v in self._properties.items()]

    @properties.setter
    def properties(self, keyval: dict[str, str]) -> None:
        self._properties = keyval

    def __getattr__(self, name: str) -> Any:
        """ Returns an attribute of a wrapped ``tmt.Result`` instance """
        return getattr(self._wrapped, name)


class ResultsContext:
    """
    The results context for Jinja templates.

    A class which keeps the results context (especially the result summary) for JUnit template. It
    wraps all the :py:class:`tmt.Result` instances into the :py:class:`ResultWrapper`.
    """

    def __init__(self, results: list[tmt.Result]) -> None:
        # Decorate all the tmt.Results with more attributes
        self._results: list[ResultWrapper] = [ResultWrapper(r) for r in results]

    def __iter__(self) -> Iterator[ResultWrapper]:
        """ Possibility to iterate over results by iterating an instance """
        return iter(self._results)

    def __len__(self) -> int:
        """ Returns the number of results """
        return len(self._results)

    @functools.cached_property
    def passed(self) -> list[ResultWrapper]:
        """ Returns results of passed tests """
        return [r for r in self._results if r.result == ResultOutcome.PASS]

    @functools.cached_property
    def skipped(self) -> list[ResultWrapper]:
        """ Returns results of skipped tests """
        return [r for r in self._results if r.result == ResultOutcome.INFO]

    @functools.cached_property
    def failed(self) -> list[ResultWrapper]:
        """ Returns results of failed tests """
        return [r for r in self._results if r.result == ResultOutcome.FAIL]

    @functools.cached_property
    def errored(self) -> list[ResultWrapper]:
        """ Returns results of tests with error/warn outcome """
        return [r for r in self._results if r.result in [
                ResultOutcome.ERROR,
                ResultOutcome.WARN]]

    @functools.cached_property
    def duration(self) -> int:
        """ Returns the total duration of all tests in seconds """
        # cast: mypy does not understand the proxy-ness of `ResultWrapper`. `r.duration`
        # will exists, therefore adding a `cast` to convince mypy the list is pretty much
        # nothing but the list of results.
        return sum(
            duration_to_seconds(r.duration) or 0 for r in cast(list[tmt.Result], self._results))


def make_junit_xml(
        phase: tmt.steps.report.ReportPlugin[Any],
        flavor: str = DEFAULT_FLAVOR_NAME,
        template_path: Optional[Path] = None,
        include_output_log: bool = True,
        prettify: bool = True,
        results_context: Optional[ResultsContext] = None,
        **extra_variables: Any
        ) -> str:
    """
    Create JUnit XML file and return the data.

    :param phase: instance of a :py:class:`tmt.steps.report.ReportPlugin`.
    :param flavor: name of a JUnit flavor to generate.
    :param template_path: if set, the provided template will be used instead of a pre-defined
        flavor template. In this case, the ``flavor`` must be set to ``custom`` value.
    :param include_output_log: if enabled, the ``<system-out>`` tags are included in the final
        template output.
    :param prettify: allows to control the XML pretty print.
    :param results_context: if set, the provided :py:class:`ResultsContext` is used in a template.
    :param extra_variables: if set, these variables get propagated into the Jinja template.
    """

    # Get the template context for tmt results
    results_context = results_context or ResultsContext(phase.step.plan.execute.results())

    # Prepare the template environment
    environment = default_template_environment()

    template_path = template_path or tmt.utils.resource_files(
        DEFAULT_TEMPLATE_DIR / Path(f'{flavor}.xml.j2'))

    # Use a FileSystemLoader for a non-custom flavor
    if flavor != CUSTOM_FLAVOR_NAME:
        environment.loader = FileSystemLoader(
            searchpath=tmt.utils.resource_files(DEFAULT_TEMPLATE_DIR))

    def _read_log(log: Path) -> str:
        """ Read the contents of a given result log """
        if not log:
            return ''

        try:
            return str(phase.step.plan.execute.read(log))
        except tmt.utils.FileError:
            return ''

    environment.filters.update({
        'read_log': _read_log,
        'duration_to_seconds': duration_to_seconds,
        'failures': tmt.result.Result.failures,
        })

    # Explicitly enable the autoescape because it's disabled by default by tmt.
    # See /teemtee/tmt/issues/2873 for more info.
    environment.autoescape = select_autoescape(enabled_extensions=('xml.j2'))

    xml_data = render_template_file(
        template_path,
        environment,
        RESULTS=results_context,
        PLAN=phase.step.plan,
        INCLUDE_OUTPUT_LOG=include_output_log,
        **extra_variables)

    # Try to use lxml to check the flavor XML schema and prettify the final XML
    # output.
    try:
        from lxml import etree
    except ImportError:
        phase.warn(
            "Install 'tmt[report-junit]' to support neater JUnit XML output and the XML schema "
            "validation against the XSD.")
        return xml_data

    xml_parser_kwargs: dict[str, Any] = {
        'remove_blank_text': prettify,
        'schema': None,
        }

    # The schema check must be done only for a non-custom JUnit flavors
    if flavor != CUSTOM_FLAVOR_NAME:
        xsd_schema_path = Path(tmt.utils.resource_files(
            Path(f'steps/report/junit/schemas/{flavor}.xsd')))

        schema_root: XMLElement = etree.XML(xsd_schema_path.read_bytes())
        xml_parser_kwargs['schema'] = etree.XMLSchema(schema_root)
    else:
        phase.warn(
            f"The '{CUSTOM_FLAVOR_NAME}' JUnit flavor is used, you are solely responsible "
            "for the validity of the XML schema.")

        if prettify:
            phase.warn(f"The pretty print is always disabled for '{CUSTOM_FLAVOR_NAME}' JUnit "
                       "flavor.")

        xml_parser_kwargs['remove_blank_text'] = prettify = False

    xml_parser = etree.XMLParser(**xml_parser_kwargs)
    try:
        # S320: Parsing of untrusted data is known to be vulnerable to XML
        # attacks.
        tree_root: XMLElement = etree.fromstring(xml_data, xml_parser)  # noqa: S320

    except etree.XMLSyntaxError as e:
        phase.warn(
            'The generated XML output is not a valid XML file or it is not valid against the '
            'XSD schema.')

        if flavor != CUSTOM_FLAVOR_NAME:
            phase.warn('Please, report this problem to project maintainers.')

        for err in e.error_log:
            phase.warn(str(err))

        # Return the prettified XML without checking the XSD
        del xml_parser_kwargs['schema']

        try:
            tree_root = etree.fromstring(  # noqa: S320
                xml_data, etree.XMLParser(**xml_parser_kwargs))
        except etree.XMLSyntaxError as error:
            phase.verbose('rendered XML', xml_data, 'red')
            raise tmt.utils.ReportError(
                'The generated XML output is not a valid XML file. Use `--verbose` argument '
                'to show the output.') from error

    # Do not be fooled by the `encoding` parameter: even with `utf-8`,
    # `tostring()` will still return bytes. `unicode`, on the other
    # hand, would give us a string, but then, no XML declaration.
    # So, we get bytes, and we need to apply `decode()` on our own.
    xml_output: bytes = etree.tostring(
        tree_root,
        xml_declaration=True,
        pretty_print=prettify,
        # The 'utf-8' encoding must be used instead of 'unicode', otherwise
        # the XML declaration is not included in the output.
        encoding='utf-8')

    return str(xml_output.decode('utf-8'))


@dataclasses.dataclass
class ReportJUnitData(tmt.steps.report.ReportStepData):
    file: Optional[Path] = field(
        default=None,
        option='--file',
        metavar='PATH',
        help='Path to the file to store JUnit to.',
        normalize=tmt.utils.normalize_path)

    flavor: str = field(
        default=DEFAULT_FLAVOR_NAME,
        option='--flavor',
        choices=[DEFAULT_FLAVOR_NAME, CUSTOM_FLAVOR_NAME],
        help='Name of a JUnit flavor to generate.')

    template_path: Optional[Path] = field(
        default=None,
        option='--template-path',
        metavar='TEMPLATE_PATH',
        help='Path to a custom template file to use for JUnit creation.',
        normalize=tmt.utils.normalize_path)

    prettify: bool = field(
        default=True,
        option=('--prettify / --no-prettify'),
        is_flag=True,
        show_default=True,
        help=f"""
            Enable the XML pretty print for generated JUnit file. This option is always disabled
            for '{CUSTOM_FLAVOR_NAME}' template flavor.
            """
        )

    include_output_log: bool = field(
        default=True,
        option=('--include-output-log / --no-include-output-log'),
        is_flag=True,
        show_default=True,
        help='Include full standard output in resulting xml file.')


@tmt.steps.provides_method('junit')
class ReportJUnit(tmt.steps.report.ReportPlugin[ReportJUnitData]):
    """
    Save test results in chosen JUnit flavor format.

    When flavor is set to custom, the ``template-path`` with a path to a custom template must be
    provided.

    When ``file`` is not specified, output is written into a file named ``junit.xml`` located in
    the current workdir.
    """

    _data_class = ReportJUnitData

    def check_options(self) -> None:
        """ Check the module options """

        if self.data.flavor == 'custom' and not self.data.template_path:
            raise tmt.utils.ReportError(
                "The 'custom' flavor requires the '--template-path' argument.")

        if self.data.flavor != 'custom' and self.data.template_path:
            raise tmt.utils.ReportError(
                "The '--template-path' can be used only with '--flavor=custom'.")

    def prune(self, logger: tmt.log.Logger) -> None:
        """ Do not prune generated junit report """

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """ Read executed tests and write junit """
        super().go(logger=logger)

        self.check_options()

        assert self.workdir is not None
        f_path = self.data.file or self.workdir / DEFAULT_NAME

        xml_data = make_junit_xml(
            phase=self,
            flavor=self.data.flavor,
            template_path=self.data.template_path,
            include_output_log=self.data.include_output_log,
            prettify=self.data.prettify)
        try:
            f_path.write_text(xml_data)
            self.info('output', f_path, 'yellow')
        except Exception as error:
            raise tmt.utils.ReportError(f"Failed to write the output '{f_path}'.") from error
