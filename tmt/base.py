""" Base Metadata Classes """

import copy
import dataclasses
import enum
import itertools
import os
import re
import shutil
import sys
import tempfile
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    Generator,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    )

import fmf
import fmf.base
import fmf.utils
import jsonschema
from click import confirm, echo, style
from fmf.utils import listed
from ruamel.yaml.error import MarkedYAMLError

import tmt.export
import tmt.frameworks
import tmt.identifier
import tmt.lint
import tmt.log
import tmt.plugins
import tmt.steps
import tmt.steps.discover
import tmt.steps.execute
import tmt.steps.finish
import tmt.steps.prepare
import tmt.steps.provision
import tmt.steps.report
import tmt.templates
import tmt.utils
from tmt.lint import LinterOutcome, LinterReturn
from tmt.result import Result, ResultOutcome
from tmt.utils import (
    Command,
    EnvironmentType,
    FmfContext,
    Path,
    ShellScript,
    WorkdirArgumentType,
    field,
    git_clone,
    normalize_shell_script,
    verdict,
    )

if sys.version_info >= (3, 8):
    from typing import Literal, TypedDict
else:
    from typing_extensions import Literal, TypedDict

if TYPE_CHECKING:
    import tmt.cli


T = TypeVar('T')

# Default test duration is 5m for individual tests discovered from L1
# metadata and 1h for scripts defined directly in plans (L2 metadata).
DEFAULT_TEST_DURATION_L1 = '5m'
DEFAULT_TEST_DURATION_L2 = '1h'
DEFAULT_ORDER = 50

# How many already existing lines should tmt run --follow show
FOLLOW_LINES = 10

# Obsoleted test keys
OBSOLETED_TEST_KEYS = "relevancy coverage".split()

# Unofficial temporary test keys
EXTRA_TEST_KEYS = (
    "extra-nitrate extra-hardware extra-pepa "
    "extra-summary extra-task id".split())

# Unofficial temporary story keys
EXTRA_STORY_KEYS = ("id".split())

SECTIONS_HEADINGS = {
    'Setup': ['<h1>Setup</h1>'],
    'Test': ['<h1>Test</h1>',
             '<h1>Test .*</h1>'],
    'Step': ['<h2>Step</h2>',
             '<h2>Test Step</h2>'],
    'Expect': ['<h2>Expect</h2>',
               '<h2>Result</h2>',
               '<h2>Expected Result</h2>'],
    'Cleanup': ['<h1>Cleanup</h1>']
    }


#
# fmf id types
#
# See https://fmf.readthedocs.io/en/latest/concept.html#identifiers for
# formal specification.
#

# A "raw" fmf id as stored in fmf node data, i.e. as a mapping with various keys.
# Used for a brief moment, to annotate raw fmf data before they are converted
# into FmfId instances.
class _RawFmfId(TypedDict, total=False):
    url: Optional[str]
    ref: Optional[str]
    path: Optional[str]
    name: Optional[str]


# An internal fmf id representation.
@dataclasses.dataclass
class FmfId(
        tmt.utils.SpecBasedContainer[_RawFmfId, _RawFmfId],
        tmt.utils.SerializableContainer,
        tmt.export.Exportable['FmfId']):

    # The list of valid fmf id keys
    VALID_KEYS: ClassVar[List[str]] = ['url', 'ref', 'path', 'name']

    #: Keys that are present, might be set, but shall not be exported.
    NONEXPORTABLE_KEYS: ClassVar[List[str]] = ['fmf_root', 'git_root', 'default_branch']

    # Save context of the ID for later - there are places where it matters,
    # e.g. to not display `ref` under some conditions.
    fmf_root: Optional[Path] = None
    git_root: Optional[Path] = None
    default_branch: Optional[str] = None

    url: Optional[str] = None
    ref: Optional[str] = None
    path: Optional[Path] = None
    name: Optional[str] = None

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_dict(self) -> _RawFmfId:  # type: ignore[override]
        """ Return keys and values in the form of a dictionary """

        return cast(_RawFmfId, super().to_dict())

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_minimal_dict(self) -> _RawFmfId:  # type: ignore[override]
        """ Convert to a mapping with unset keys omitted """

        return cast(_RawFmfId, super().to_minimal_dict())

    # TODO: make this declarative, Exportable should support this feature
    # out of the box. Maybe even add a parameter for field().
    @classmethod
    def _drop_nonexportable(cls, exported: _RawFmfId) -> _RawFmfId:
        # ignore[misc]: since `exported` is a typed dict, only literals can be used as keys
        for key in cls.NONEXPORTABLE_KEYS:
            exported.pop(key, None)  # type: ignore[misc]

        return exported

    def to_spec(self) -> _RawFmfId:
        """ Convert to a form suitable for saving in a specification file """

        spec = self.to_dict()

        if self.path is not None:
            spec['path'] = str(self.path)

        return self._drop_nonexportable(spec)

    def to_minimal_spec(self) -> _RawFmfId:
        """ Convert to specification, skip default values """

        spec = cast(_RawFmfId, super().to_minimal_spec())

        if self.path is not None:
            spec['path'] = str(self.path)

        return self._drop_nonexportable(spec)

    @classmethod
    def from_spec(cls, raw: _RawFmfId) -> 'FmfId':
        """ Convert from a specification file or from a CLI option """

        # TODO: with mandatory validation, this can go away.
        ref = raw.get('ref', None)
        if not isinstance(ref, (type(None), str)):
            # TODO: deliver better key address
            raise tmt.utils.NormalizationError('ref', ref, 'unset or a string')

        fmf_id = FmfId()

        for key in ('url', 'ref', 'name'):
            setattr(fmf_id, key, cast(Optional[str], raw.get(key, None)))

        for key in ('path',):
            raw_path = cast(Optional[str], raw.get(key, None))
            setattr(fmf_id, key, Path(raw_path) if raw_path is not None else None)

        return fmf_id

    def validate(self) -> Tuple[bool, str]:
        """
        Validate fmf id and return a human readable error

        Return a tuple (boolean, message) as the result of validation.
        The boolean specifies the validation result and the message
        the validation error. In case the FMF id is valid, return an empty
        string as the message.
        """
        # Validate remote id and translate to human readable errors
        try:
            # Simple asdict() is not good enough, fmf does not like keys that exist but are `None`.
            # Don't include those.
            node_data = {
                key: value for key, value in self.items()
                if value is not None
                }
            if self.path:
                node_data['path'] = str(self.path)
            fmf.base.Tree.node(node_data)
        except fmf.utils.GeneralError as error:
            # Map fmf errors to more user friendly alternatives
            error_map: List[Tuple[str, str]] = [
                ('git clone', f"repo '{self.url}' cannot be cloned"),
                ('git checkout', f"git ref '{self.ref}' is invalid"),
                ('directory path', f"path '{self.path}' is invalid"),
                ('tree root', f"No tree found in repo '{self.url}', missing an '.fmf' directory?")
                ]

            stringified_error = str(error)

            errors = [message for needle, message in error_map if needle in stringified_error]
            return (False, errors[0] if errors else stringified_error)

        return (True, '')

    # cast: expected, we do want to return more specific type than the one returned by the
    # existing serialization.
    def _export(
            self,
            *,
            keys: Optional[List[str]] = None
            ) -> tmt.export._RawExportedInstance:

        spec = self.to_minimal_spec()

        spec = self._drop_nonexportable(spec)

        return cast(tmt.export._RawExportedInstance, spec)


#
# Various types describing constructs as stored in "raw" fmf node data.
# Used for a brief moment, to annotate raw fmf data before they are converted
# into their internal representations.
#

#
# A type describing the raw form of the core `link` attribute. See
# https://tmt.readthedocs.io/en/stable/spec/core.html#link for its
# formal specification. Internally, a link is represented by a `Link`
# class instance, and types below describe the raw data coming from Fmf
# nodes and CLI options.


# Link relations.
_RawLinkRelationName = Literal[
    'verifies', 'verified-by',
    'implements', 'implemented-by',
    'documents', 'documented-by',
    'blocks', 'blocked-by',
    'duplicates', 'duplicated-by',
    'parent', 'child',
    'relates', 'test-script',
    # Special case: not a relation, but it can appear where relations appear in
    # link data structures.
    'note'
    ]

# Link target - can be either a string (like test case name or URL), or an fmf id.
_RawLinkTarget = Union[str, _RawFmfId]

# Basic "relation-aware" link - essentialy a mapping with one key/value pair.
_RawLinkRelation = Dict[_RawLinkRelationName, _RawLinkTarget]

# A single link can be represented as a string or FMF ID (meaning only target is specified),
# or a "relation-aware" link aka mapping defined above.
_RawLink = Union[
    str,
    _RawFmfId,
    _RawLinkRelation
    ]

# Collection of links - can be either a single link, or a list of links, and all
# link forms may be used together.
_RawLinks = Union[
    _RawLink,
    List[_RawLink]
    ]


# A type describing `adjust` content. See
# https://tmt.readthedocs.io/en/stable/spec/core.html#adjust for its formal specification.
#
# The type is incomplete in the sense it does not describe all keys it may contain,
# like `environment` or `provision`, and focuses only on the keys defined for `adjust`
# itself.
_RawAdjustRule = TypedDict(
    '_RawAdjustRule',
    {
        'when': Optional[str],
        'continue': Optional[bool],
        'because': Optional[str]
        }
    )


# Types describing content accepted by various require-like keys: strings, fmf ids,
# paths, or lists mixing various types.
#
# See https://tmt.readthedocs.io/en/latest/spec/tests.html#require

class DependencySimple(str):
    """ A basic, simple dependency, usually a package """

    # ignore[override]: expected, we do want to accept and return more
    # specific types than those declared in superclass.
    @classmethod
    def from_spec(cls, spec: str) -> 'DependencySimple':
        return DependencySimple(spec)

    def to_spec(self) -> str:
        return str(self)

    def to_minimal_spec(self) -> str:
        return self.to_spec()


class _RawDependencyFmfId(_RawFmfId):
    destination: Optional[str]
    nick: Optional[str]
    type: Optional[str]


@dataclasses.dataclass
class DependencyFmfId(
        FmfId,
        # Repeat the SpecBasedContainer, with more fitting in/out spec type.
        tmt.utils.SpecBasedContainer[_RawDependencyFmfId, _RawDependencyFmfId]):
    """
    A fmf ID as a dependency.

    Not a pure fmf ID though, the form accepted by `require` & co. allows
    several extra keys.
    """

    VALID_KEYS: ClassVar[List[str]] = [*FmfId.VALID_KEYS, 'destination', 'nick', 'type']

    destination: Optional[Path] = None
    nick: Optional[str] = None
    # fmf id dependency is a beakerlib dependency, as of now, there is no other
    # allowed `type` value.
    type: str = 'library'

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_dict(self) -> _RawDependencyFmfId:  # type: ignore[override]
        return cast(_RawDependencyFmfId, super().to_dict())

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_minimal_dict(self) -> _RawDependencyFmfId:  # type: ignore[override]
        """ Convert to a mapping with unset keys omitted """

        return cast(_RawDependencyFmfId, super().to_minimal_dict())

    def to_spec(self) -> _RawDependencyFmfId:
        """ Convert to a form suitable for saving in a specification file """

        spec = self.to_dict()

        if self.destination is not None:
            spec['destination'] = str(self.destination)

        return spec

    def to_minimal_spec(self) -> _RawDependencyFmfId:
        """ Convert to specification, skip default values """

        spec = self.to_minimal_dict()

        if self.destination is not None:
            spec['destination'] = str(self.destination)

        return spec

    # ignore[override]: expected, we do want to accept and return more
    # specific types than those declared in superclass.
    @classmethod
    def from_spec(cls, raw: _RawDependencyFmfId) -> 'DependencyFmfId':  # type: ignore[override]
        """ Convert from a specification file or from a CLI option """

        # TODO: with mandatory validation, this can go away.
        ref = raw.get('ref', None)
        if not isinstance(ref, (type(None), str)):
            # TODO: deliver better key address
            raise tmt.utils.NormalizationError('ref', ref, 'unset or a string')

        fmf_id = DependencyFmfId()

        for key in ('url', 'ref', 'name', 'nick'):
            setattr(fmf_id, key, cast(Optional[str], raw.get(key, None)))

        for key in ('path', 'destination'):
            raw_path = cast(Optional[str], raw.get(key, None))
            setattr(fmf_id, key, Path(raw_path) if raw_path is not None else None)

        return fmf_id


class _RawDependencyFile(TypedDict):
    type: Optional[str]
    pattern: Optional[List[str]]


@dataclasses.dataclass
class DependencyFile(
        tmt.utils.SpecBasedContainer[_RawDependencyFile, _RawDependencyFile],
        tmt.utils.SerializableContainer,
        tmt.export.Exportable['DependencyFile']):
    VALID_KEYS: ClassVar[List[str]] = ['type', 'pattern']

    type: str = 'file'
    pattern: List[str] = tmt.utils.field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list)

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_dict(self) -> _RawDependencyFile:  # type: ignore[override]
        """ Return keys and values in the form of a dictionary """
        return cast(_RawDependencyFile, super().to_dict())

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def to_minimal_dict(self) -> _RawDependencyFile:  # type: ignore[override]
        """ Convert to a mapping with unset keys omitted """
        return cast(_RawDependencyFile, super().to_minimal_dict())

    # ignore[override]: expected, we do want to accept and return more
    # specific types than those declared in superclass.
    @classmethod
    def from_spec(cls, raw: _RawDependencyFile) -> 'DependencyFile':
        """ Convert from a specification file or from a CLI option """
        dependency = cls()

        raw_patterns = raw.get('pattern', [])
        if not raw_patterns:
            raise tmt.utils.SpecificationError(f'Missing pattern for file require: {raw}')

        if isinstance(raw_patterns, str):
            dependency.pattern.append(raw_patterns)
        else:
            dependency.pattern += [
                str(pattern) for pattern in raw_patterns
                ]

        return dependency

    @staticmethod
    def validate() -> Tuple[bool, str]:
        """
        Validate file dependency and return a human readable error

        There is no way to check validity of type or pattern string at
        this time. Return a tuple (boolean, message) as the result of
        validation. The boolean specifies the validation result and the
        message the validation error. In case the file dependency is
        valid, return an empty string as the message.
        """
        return True, ''


_RawDependencyItem = Union[str, _RawDependencyFmfId, _RawDependencyFile]
_RawDependency = Union[_RawDependencyItem, List[_RawDependencyItem]]

Dependency = Union[DependencySimple, DependencyFmfId, DependencyFile]


def dependency_factory(raw_dependency: Optional[_RawDependencyItem]) -> Dependency:
    """ Select the correct require class """
    if isinstance(raw_dependency, dict):
        dependency_type = raw_dependency.get('type', 'library')
        if dependency_type == 'library':  # can't use isinstance check with TypedDict
            return DependencyFmfId.from_spec(raw_dependency)  # type: ignore[arg-type]
        if dependency_type == 'file':
            return DependencyFile.from_spec(raw_dependency)  # type: ignore[arg-type]

    assert isinstance(raw_dependency, str)  # check type
    return DependencySimple.from_spec(raw_dependency)


def normalize_require(
        key_address: str,
        raw_require: Optional[_RawDependency],
        logger: tmt.log.Logger) -> List[Dependency]:
    """
    Normalize content of ``require`` key.

    The requirements may be defined as either string or a special fmf id
    flavor, or a mixed list of these types. The goal here is to reduce the
    space of possibilities to a list, with fmf ids being converted to their
    internal representation.
    """

    if raw_require is None:
        return []

    if isinstance(raw_require, (str, dict)):
        return [dependency_factory(raw_require)]

    if isinstance(raw_require, list):
        return [dependency_factory(require) for require in raw_require]

    raise tmt.utils.NormalizationError(
        key_address,
        raw_require,
        'a string, a library, a file or a list of their combinations')


def assert_simple_dependencies(
        dependencies: List[Dependency],
        error_message: str,
        logger: tmt.log.Logger) -> List[DependencySimple]:
    """
    Make sure the list of dependencies consists of simple ones.

    :param dependencies: the list of requires.
    :param error_message: used for a raised exception.
    :param logger: used for logging.
    :raises GeneralError: when there is a dependency on the list which
        is not a subclass of :py:class:`tmt.base.DependencySimple`.
    """

    non_simple_dependencies = list(filter(
        lambda dependency: not isinstance(dependency, DependencySimple),
        dependencies
        ))

    if not non_simple_dependencies:
        return cast(List[DependencySimple], dependencies)

    for dependency in non_simple_dependencies:
        logger.fail(f'Invalid requirement: {dependency}')

    raise tmt.utils.GeneralError(error_message)


CoreT = TypeVar('CoreT', bound='Core')


def _normalize_link(key_address: str, value: _RawLinks, logger: tmt.log.Logger) -> 'Links':
    return Links(data=value)


@dataclasses.dataclass(repr=False)
class Core(
        tmt.utils.ValidateFmfMixin,
        tmt.utils.LoadFmfKeysMixin,
        tmt.utils.Common):
    """
    General node object

    Corresponds to given fmf.Tree node.
    Implements common Test, Plan and Story methods.
    Also defines L0 metadata and its manipulation.
    """

    # Core attributes (supported across all levels)
    summary: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    order: int = field(
        default=DEFAULT_ORDER,
        normalize=lambda key_address, raw_value, logger:
            DEFAULT_ORDER if raw_value is None else int(raw_value))
    link: Optional['Links'] = field(
        default=None,
        normalize=_normalize_link)
    id: Optional[str] = None
    tag: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list)
    tier: Optional[str] = field(
        default=None,
        normalize=lambda key_address, raw_value, logger:
            None if raw_value is None else str(raw_value))
    adjust: Optional[List[_RawAdjustRule]] = field(
        default_factory=list,
        normalize=lambda key_address, raw_value, logger: [] if raw_value is None
        else ([raw_value] if not isinstance(raw_value, list) else raw_value))

    _KEYS_SHOW_ORDER = [
        # Basic stuff
        'summary',
        'description',
        'enabled',
        'order',
        'id',

        # Filtering and more
        'tag',
        'tier',
        'link',
        'adjust',
        ]

    def __init__(self,
                 *,
                 node: fmf.Tree,
                 parent: Optional[tmt.utils.Common] = None,
                 logger: tmt.log.Logger,
                 **kwargs: Any) -> None:
        """ Initialize the node """
        super().__init__(node=node, logger=logger, parent=parent, name=node.name, **kwargs)

        self.node = node

        # Verify id is not inherited from parent.
        if self.id and not tmt.utils.is_key_origin(node, 'id'):
            raise tmt.utils.SpecificationError(
                f"The 'id' key '{node.get('id')}' in '{self.name}' "
                f"is inherited from parent, should be defined in a leaf.")

        # Store original metadata with applied defaults and including
        # keys which are not defined in the L1 metadata specification
        # Once the whole node has been initialized,
        # self._update_metadata() must be called to work correctly.
        self._metadata = self.node.data.copy()

    def __str__(self) -> str:
        """ Node name """
        return self.name

    @classmethod
    def from_tree(cls: Type[T], tree: 'tmt.Tree') -> List[T]:
        """
        Gather list of instances of this class in a given tree.

        Helpful when looking for objects of a class derived from :py:class:`Core`
        in a given tree, encapsulating the mapping between core classes and tree
        search methods.

        :param tree: tree to search for objects.
        """

        return cast(List[T], getattr(tree, f'{cls.__name__.lower()}s')())

    def _update_metadata(self) -> None:
        """ Update the _metadata attribute """
        self._metadata.update(self._export())
        self._metadata['name'] = self.name

    def _show_additional_keys(self) -> None:
        """ Show source files """
        if self.id is not None:
            echo(tmt.utils.format('id', self.id, key_color='magenta'))
        echo(tmt.utils.format('sources', self.node.sources, key_color='magenta'))
        self._fmf_id()
        web_link = self.web_link()
        if web_link is not None:
            echo(tmt.utils.format('web', web_link, key_color='magenta', wrap=False))

    def _fmf_id(self) -> None:
        """ Show fmf identifier """
        echo(tmt.utils.format('fmf-id', cast(Dict[str, Any],
             self.fmf_id.to_minimal_spec()), key_color='magenta'))

    # TODO: cached_property candidates
    @property
    def fmf_root(self) -> Path:
        return Path(self.node.root)

    @property
    def git_root(self) -> Optional[Path]:
        return tmt.utils.git_root(fmf_root=self.fmf_root, logger=self._logger)

    # Caching properties does not play nicely with mypy and annotations,
    # and constructing a workaround would be hard because of support of
    # Python 3.6 tmt wishes to maintain.
    # https://github.com/python/mypy/issues/5858
    @property
    def fmf_id(self) -> FmfId:
        """ Return full fmf identifier of the node """

        # When the object is built from an fmf node without a root, it's
        # probably not possible for the object to have any fmf ID in the
        # context of a non-existent fmf tree.
        if self.node.root is None:
            return FmfId()

        return tmt.utils.fmf_id(
            name=self.name,
            fmf_root=self.fmf_root,
            always_get_ref=True,
            logger=self._logger)

    def web_link(self) -> Optional[str]:
        """ Return a clickable web link to the fmf metadata location """
        if self.fmf_id.ref is None or self.fmf_id.url is None:
            return None

        # Detect relative path of the last source from the metadata tree root
        relative_path = Path(self.node.sources[-1]).relative_to(self.node.root)
        relative_path = Path('/') if str(relative_path) == '.' else Path('/') / relative_path

        # Add fmf path if the tree is nested deeper in the git repo
        if self.fmf_id.path:
            relative_path = self.fmf_id.path / relative_path.relative_to('/')

        return tmt.utils.web_git_url(self.fmf_id.url, self.fmf_id.ref, relative_path)

    @classmethod
    def _save_cli_context(cls, context: 'tmt.cli.Context') -> None:
        """ Save provided command line context for future use """
        super()._save_cli_context(context)

        # Handle '.' as an alias for the current working directory
        names = cls._opt('names')
        if names is not None and '.' in names:
            assert context.obj.tree.root is not None  # narrow type
            root = context.obj.tree.root
            current = Path.cwd()
            # Handle special case when directly in the metadata root
            if current.resolve() == root.resolve():
                pattern = '/'
            # Prepare path from the tree root to the current directory
            else:
                # Prevent matching common prefix from other directories
                pattern = f"{current.relative_to(root)}(/|$)"
            cls._cli_options['names'] = tuple(
                pattern if name == '.' else name for name in names)

    def name_and_summary(self) -> str:
        """ Node name and optional summary """
        if self.summary:
            return f'{self.name} ({self.summary})'
        return self.name

    def ls(self, summary: bool = False) -> None:
        """ List node """
        echo(style(self.name, fg='red'))
        if summary and self.summary:
            echo(tmt.utils.format('summary', self.summary))

    def _export(self, *, keys: Optional[List[str]] = None) -> tmt.export._RawExportedInstance:
        if keys is None:
            keys = self._keys()

        # Always include node name, add requested keys, ignore adjust
        data: Dict[str, Any] = {'name': self.name}
        for key in keys:
            # TODO: provide more mature solution for https://github.com/teemtee/tmt/issues/1688
            # Until that, do not export fields that start with an underscore, to avoid leaking
            # "private" object members.
            if key.startswith('_'):
                continue

            # TODO: override the method, or provide better way to filter out this class var
            if key == '_export_plugin_registry':
                continue

            if key == 'adjust':
                continue

            value = getattr(self, key)

            if key == 'link' and value is not None:
                # TODO: links must be saved in a form that can be than crunched by
                # Links.__init__() method - it is tempting to use to_serialized()
                # and from_unserialized(), but we don't use unserialization code
                # when loading saved data back, so we can't go this way. Yet.
                data[key] = cast('Links', value).to_spec()

            elif isinstance(value, FmfId):
                data[key] = value.to_dict()

            else:
                data[key] = value

        return data

    def _lint_keys(self, additional_keys: List[str]) -> List[str]:
        """ Return list of invalid keys used, empty when all good """
        known_keys = additional_keys + self._keys()
        return [key for key in self.node.get() if key not in known_keys]

    def lint_validate(self) -> LinterReturn:
        """ C000: fmf node should pass the schema validation """

        schema_name = self.__class__.__name__.lower()

        errors = tmt.utils.validate_fmf_node(self.node, f'{schema_name}.yaml', self._logger)

        if errors:
            # A bit of error formatting. It is possible to use str(error), but the result
            # is a bit too JSON-ish. Let's present an error message in a way that helps
            # users to point finger on each and every issue.

            def detect_unallowed_properties(error: jsonschema.ValidationError) -> LinterReturn:
                match = re.search(
                    r"(?mi)Additional properties are not allowed \(([a-zA-Z0-9', \-]+) (?:was|were) unexpected\)",  # noqa: E501
                    str(error))

                if not match:
                    return

                for bad_property in match.group(1).replace("'", '').replace(' ', '').split(','):
                    yield LinterOutcome.WARN, \
                        f'key "{bad_property}" not recognized by schema {error.schema["$id"]}'

            # A key not recognized, but when patternProperties are allowed. In that case,
            # the key is both not listed and not matching the pattern.
            def detect_unallowed_properties_with_pattern(
                    error: jsonschema.ValidationError) -> LinterReturn:
                match = re.search(
                    r"(?mi)'([a-zA-Z0-9', \-]+)' (?:does|do) not match any of the regexes: '([a-zA-Z0-9\-\^\+\*]+)'",  # noqa: E501
                    str(error))

                if not match:
                    return

                for bad_property in match.group(1).replace("'", '').replace(' ', '').split(','):
                    yield LinterOutcome.WARN, \
                        f'key "{bad_property}" not recognized by schema,' \
                        f' and does not match "{match.group(2)}" pattern'

            # A key value is not recognized. This is often a case with keys whose values are
            # limited by an enum, like `how`. Unfortunatelly, validator will record every mismatch
            # between a value and enum even if eventually a match is found. So it might be tempting
            # to ignore this particular kind of error - it may also indicate a genuine typo in
            # key name or completely misplaced key, so it's still necessary to report the error.
            def detect_enum_violations(error: jsonschema.ValidationError) -> LinterReturn:
                match = re.search(
                    r"(?mi)'([a-z\-]+)' is not one of \['([a-zA-Z\-]+)'\]",
                    str(error))

                if not match:
                    return

                # Older jsonpatch packages may lack this attribute
                if not hasattr(error, 'json_path'):
                    json_path = '$'

                    for elem in error.absolute_path:
                        if isinstance(elem, int):
                            json_path += f'[{elem}]'
                        else:
                            json_path += f'.{elem}'

                else:
                    json_path = error.json_path

                yield LinterOutcome.WARN, \
                    f'value of "{json_path.split(".")[-1]}" is not "{match.group(2)}"'

            for error, _ in errors:
                yield from detect_unallowed_properties(error)
                yield from detect_unallowed_properties_with_pattern(error)
                yield from detect_enum_violations(error)

                # Validation errors can have "context", a list of "sub" errors encountered during
                # validation. Interesting ones are identified & added to our error message.
                if error.context:
                    for suberror in error.context:
                        yield from detect_unallowed_properties(suberror)
                        yield from detect_unallowed_properties_with_pattern(suberror)
                        yield from detect_enum_violations(suberror)

            yield LinterOutcome.WARN, 'fmf node failed schema validation'

            return

        yield LinterOutcome.PASS, 'fmf node passes schema validation'

    def lint_summary_exists(self) -> LinterReturn:
        """ C001: summary key should be set and should be reasonably long """

        if not self.summary:
            yield LinterOutcome.WARN, 'summary key is missing'
            return

        if len(self.summary) > 50:
            yield LinterOutcome.WARN, 'summary should not exceed 50 characters'
            return

        yield LinterOutcome.PASS, 'summary key is set and is reasonably long'

    def has_link(self, needle: 'LinkNeedle') -> bool:
        """ Whether object contains specified link """

        if self.link is None:
            return False

        return self.link.has_link(needle=needle)


Node = Core


@dataclasses.dataclass(repr=False)
class Test(
        Core,
        tmt.export.Exportable['Test'],
        tmt.lint.Lintable['Test']):
    """ Test object (L1 Metadata) """

    # Basic test information
    contact: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list
        )
    component: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list
        )

    # Test execution data
    # TODO: mandatory schema validation would remove the need for Optional...
    # `test` is mandatory, must exist, so how to initialize if it's missing :(
    test: Optional[ShellScript] = field(
        default=None,
        normalize=normalize_shell_script)
    path: Optional[Path] = field(
        default=None,
        normalize=lambda key_address, raw_value, logger:
            None if raw_value is None else Path(raw_value))
    framework: str = "shell"
    manual: bool = False
    require: List[Dependency] = field(
        default_factory=list,
        normalize=normalize_require)
    recommend: List[Dependency] = field(
        default_factory=list,
        normalize=normalize_require)
    environment: tmt.utils.EnvironmentType = field(default_factory=dict)

    duration: str = DEFAULT_TEST_DURATION_L1
    result: str = 'respect'

    where: List[str] = field(default_factory=list)

    serialnumber: int = 0

    returncode: Optional[int] = None
    starttime: Optional[str] = None
    endtime: Optional[str] = None
    real_duration: Optional[str] = None
    _reboot_count: int = 0

    _KEYS_SHOW_ORDER = [
        # Basic test information
        'summary',
        'description',
        'contact',
        'component',
        'id',

        # Test execution data
        'test',
        'path',
        'framework',
        'manual',
        'require',
        'recommend',
        'environment',
        'duration',
        'enabled',
        'order',
        'result',

        # Filtering attributes
        'tag',
        'tier',
        'link',
        ]

    @classmethod
    def from_dict(
            cls,
            *,
            mapping: Dict[str, Any],
            name: str,
            skip_validation: bool = False,
            raise_on_validation_error: bool = False,
            logger: tmt.log.Logger,
            **kwargs: Any) -> 'Test':
        """
        Initialize test data from a dictionary.

        Useful when data describing a test are stored in a mapping instead of an fmf node.
        """

        if not name.startswith('/'):
            raise tmt.utils.SpecificationError("Test name should start with a '/'.")

        node = fmf.Tree(mapping)
        node.name = name

        return cls(
            logger=logger,
            node=node,
            skip_validation=skip_validation,
            raise_on_validation_error=raise_on_validation_error,
            **kwargs)

    def __init__(
            self,
            *,
            node: fmf.Tree,
            skip_validation: bool = False,
            raise_on_validation_error: bool = False,
            logger: tmt.log.Logger,
            **kwargs: Any) -> None:
        """
        Initialize test data from an fmf node or a dictionary

        The following two methods are supported:

            Test(node)
        """

        # Path defaults to the directory where metadata are stored or to
        # the root '/' if fmf metadata were not stored on the filesystem
        #
        # NOTE: default value of `path` attribute is not known when attribute
        # is declared, therefore we need to compute the default value and
        # assign it to attribute *before* calling superclass and its handy
        # node key extraction.
        try:
            directory = Path(node.sources[-1]).parent
            relative_path = directory.relative_to(Path(node.root))
            default_path = Path('/') if relative_path == Path('.') else Path('/') / relative_path
        except (AttributeError, IndexError):
            default_path = Path('/')

        self.path = default_path

        super().__init__(
            node=node,
            logger=logger,
            skip_validation=skip_validation,
            raise_on_validation_error=raise_on_validation_error,
            **kwargs)

        # TODO: As long as validation is optional, a missing `test` key would be reported
        # as such but won't stop tmt from moving on.
        if self.test is None:
            raise tmt.utils.SpecificationError(
                f"The 'test' attribute in '{self.name}' must be defined.")

        if self.framework == 'beakerlib':
            self.require.append(DependencySimple('beakerlib'))

        self._update_metadata()

    def _export(self, *, keys: Optional[List[str]] = None) -> tmt.export._RawExportedInstance:
        data = super()._export(keys=keys)

        for key, value in data.items():
            if key in ('require', 'recommend') and value:
                data[key] = [
                    dependency.to_minimal_spec() for dependency in cast(List[Dependency], value)
                    ]

            # Combining `if` branches using `or` here would result in long, complex line.
            elif key == 'test' and isinstance(value, ShellScript):  # noqa: SIM114
                data[key] = str(value)

            elif key == 'path' and isinstance(value, Path):
                data[key] = str(value)

        return data

    @staticmethod
    def overview(tree: 'Tree') -> None:
        """ Show overview of available tests """
        tests = [
            style(str(test), fg='red') for test in tree.tests()]
        echo(style(
            'Found {}{}{}.'.format(
                listed(tests, 'test'),
                ': ' if tests else '',
                listed(tests, max=12)
                ), fg='blue'))

    @staticmethod
    def create(
            *,
            name: str,
            template: str,
            path: Path,
            force: bool = False,
            dry: Optional[bool] = None,
            logger: tmt.log.Logger) -> None:
        """ Create a new test """
        if dry is None:
            dry = Test._opt('dry')

        # Create directory
        if name == '.':
            directory_path = Path.cwd()
        else:
            directory_path = path / name.lstrip('/')
            tmt.utils.create_directory(
                path=directory_path,
                name='test directory',
                dry=dry,
                logger=logger)

        # Create metadata
        try:
            metadata_path = directory_path / 'main.fmf'
            tmt.utils.create_file(
                path=metadata_path,
                content=tmt.templates.TEST_METADATA[template],
                name='test metadata',
                dry=dry,
                force=force)
        except KeyError:
            raise tmt.utils.GeneralError(f"Invalid template '{template}'.")

        # Create script
        script_path = directory_path / 'test.sh'
        try:
            content = tmt.templates.TEST[template]
        except KeyError:
            raise tmt.utils.GeneralError(f"Invalid template '{template}'.")
        tmt.utils.create_file(
            path=script_path, content=content,
            name='test script', dry=dry, force=force, mode=0o755)

    @property
    def manual_test_path(self) -> Path:
        assert self.manual, 'Test is not manual yet path to manual instructions was requested'

        assert self.test
        assert self.path

        return Path(self.node.root) / self.path.unrooted() / str(self.test)

    @property
    def test_framework(self) -> tmt.frameworks.TestFrameworkClass:
        framework = tmt.frameworks._FRAMEWORK_PLUGIN_REGISTRY.get_plugin(self.framework)

        if framework is None:
            raise tmt.utils.SpecificationError(f"Unknown framework '{self.framework}'.")

        return framework

    def show(self) -> None:
        """ Show test details """
        self.ls()
        for key in self._KEYS_SHOW_ORDER:
            value = getattr(self, key)
            if key == 'link' and value is not None:
                value.show()
                continue
            # No need to show the default order
            if key == 'order' and value == DEFAULT_ORDER:
                continue
            if key in ('require', 'recommend') and value:
                echo(tmt.utils.format(
                    key,
                    [dependency.to_minimal_spec() for dependency in cast(List[Dependency], value)]
                    ))
                continue
            if value not in [None, [], {}]:
                echo(tmt.utils.format(key, value))
        if self.verbosity_level:
            self._show_additional_keys()
        if self.verbosity_level >= 2:
            # Print non-empty unofficial attributes
            for key in sorted(self.node.get().keys()):
                # Already asked to be printed
                if key in self._keys():
                    continue
                value = self.node.get(key)
                if value not in [None, [], {}]:
                    echo(tmt.utils.format(key, value, key_color='blue'))

    # FIXME - Make additional attributes configurable
    def lint_unknown_keys(self) -> LinterReturn:
        """ T001: all keys are known """

        # We don't want adjust in show/export so it is not yet in Test._keys
        invalid_keys = self._lint_keys(EXTRA_TEST_KEYS + OBSOLETED_TEST_KEYS + ['adjust'])

        if invalid_keys:
            for key in invalid_keys:
                yield LinterOutcome.FAIL, f'unknown key "{key}" is used'

            return

        yield LinterOutcome.PASS, 'correct keys are used'

    def lint_defined_test(self) -> LinterReturn:
        """ T002: test script must be defined """

        if not self.test:
            yield LinterOutcome.FAIL, 'test script is not defined'
            return

        yield LinterOutcome.PASS, 'test script is defined'

    def lint_absolute_path(self) -> LinterReturn:
        """ T003: test directory path must be absolute """

        if not self.path:
            yield LinterOutcome.FAIL, 'directory path is not set'
            return

        if not self.path.is_absolute():
            yield LinterOutcome.FAIL, 'directory path is not absolute'
            return

        yield LinterOutcome.PASS, 'directory path is absolute'

    def lint_path_exists(self) -> LinterReturn:
        """ T004: test directory path must exist """

        if not self.path:
            yield LinterOutcome.FAIL, 'directory path is not set'
            return

        test_path = Path(self.node.root) / self.path.unrooted()

        if not test_path.exists():
            yield LinterOutcome.FAIL, f"test path '{test_path}' does not exist"
            return

        yield LinterOutcome.PASS, f"test path '{test_path}' does exist"

    def lint_legacy_relevancy_rules(self) -> LinterReturn:
        """ T005: relevancy has been obsoleted by adjust """

        relevancy = self.node.get('relevancy')

        if not relevancy:
            yield LinterOutcome.SKIP, 'legacy relevancy not detected'
            return

        # Convert into adjust rules if --fix enabled
        if not self.opt('fix'):
            yield LinterOutcome.FAIL, 'relevancy has been obsoleted by adjust'
            return

        if not tmt.utils.is_key_origin(self.node, 'relevancy'):
            yield LinterOutcome.FAIL, \
                'relevancy detected but inherited from test parent, please, fix manually'
            return

        filename = self.node.sources[-1]
        metadata = tmt.utils.yaml_to_dict(self.read(filename))

        metadata['adjust'] = tmt.convert.relevancy_to_adjust(metadata.pop('relevancy'))
        self.write(filename, tmt.utils.dict_to_yaml(metadata))

        yield LinterOutcome.FIXED, 'relevancy converted into adjust'

    def lint_legacy_coverage_key(self) -> LinterReturn:
        """ T006: coverage has been obsoleted by link """

        coverage = self.node.get('coverage')

        if coverage is None:
            yield LinterOutcome.SKIP, "legacy 'coverage' field not detected"
            return

        yield LinterOutcome.FAIL, "the 'coverage' field has been obsoleted by 'link'"

    # Check if the format of Markdown file respects the specification
    # https://tmt.readthedocs.io/en/latest/spec/tests.html#manual
    def lint_manual_test_path_exists(self) -> LinterReturn:
        """ T007: manual test path is not an actual path """

        if not self.manual:
            yield LinterOutcome.SKIP, 'not a manual test'
            return

        if not self.path:
            yield LinterOutcome.FAIL, 'directory path is not set'
            return

        if not self.manual_test_path.exists():
            yield LinterOutcome.FAIL, f'manual test path "{self.manual_test_path}" does not exist'
            return

        yield LinterOutcome.PASS, f'manual test path "{self.manual_test_path}" does exist'

    def lint_manual_valid_markdown(self) -> LinterReturn:
        """ T008: manual test should be valid markdown """

        if not self.manual:
            yield LinterOutcome.SKIP, 'not a manual test'
            return

        try:
            warnings = tmt.export.check_md_file_respects_spec(self.manual_test_path)

        except tmt.utils.ConvertError as exc:
            yield LinterOutcome.FAIL, f'cannot open the manual test path: {exc}'
            return

        if warnings:
            for warning in warnings:
                # replace new-lines with a (single) space
                yield LinterOutcome.WARN, ' '.join(line.strip() for line in warning.splitlines())

            return

        yield LinterOutcome.PASS, 'correct manual test syntax'

    def lint_require_type_field(self) -> LinterReturn:
        """ T009: require fields should have type field """

        self.node.get('require')
        missing_type = []

        # Check require items have type field
        complex_dependencies = [
            dependency for dependency in self.node.get('require', [])
            if isinstance(dependency, dict)
            ]

        if not complex_dependencies:
            yield LinterOutcome.SKIP, 'library/file requirements not used'
            return

        missing_type = [
            dependency for dependency in complex_dependencies if not dependency.get('type')
            ]

        if not missing_type:
            yield LinterOutcome.PASS, 'all library/file requirements specify type'
            return

        if not self.opt('fix'):
            yield LinterOutcome.FAIL, 'library/file requirements should specify type'
            return

        filename = self.node.sources[-1]
        metadata = tmt.utils.yaml_to_dict(self.read(filename))

        if not tmt.utils.is_key_origin(self.node, 'require') \
                and all(dependency in metadata.get('require', []) for dependency in missing_type):
            yield LinterOutcome.FAIL, \
                'some library/file requirement are missing type, but inherited from test parent,' \
                ' please, fix manually'
            return

        for dependency in metadata.get('require', []):
            if not isinstance(dependency, dict) or dependency.get('type'):
                continue

            dependency['type'] = 'file' if dependency.get('pattern') else 'library'

        self.write(filename, tmt.utils.dict_to_yaml(metadata))

        yield LinterOutcome.FIXED, 'added type to requirements'


@dataclasses.dataclass(repr=False)
class Plan(
        Core,
        tmt.export.Exportable['Plan'],
        tmt.lint.Lintable['Plan']):
    """ Plan object (L2 Metadata) """

    # The class variable _cli_options need to be reassigned with a new empty
    # dictionary instance. Otherwise, it would use the shared dictionary
    # from Common class and causes error in certain cases.
    _cli_options = {}

    # `environment` and `environment-file` are NOT promoted to instance variables.
    context: FmfContext = field(
        default_factory=FmfContext,
        normalize=tmt.utils.FmfContext.from_spec)
    gate: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list)

    # When fetching remote plans we store links between the original
    # plan with the fmf id and the imported plan with the content.
    _imported_plan: Optional['Plan'] = None
    _original_plan: Optional['Plan'] = None
    _remote_plan_fmf_id: Optional[FmfId] = None

    _extra_l2_keys = [
        'context',
        'environment',
        'environment-file',
        'gate',
        ]

    def __init__(
            self,
            *,
            node: fmf.Tree,
            run: Optional['Run'] = None,
            skip_validation: bool = False,
            raise_on_validation_error: bool = False,
            logger: tmt.log.Logger,
            **kwargs: Any) -> None:
        """ Initialize the plan """
        kwargs.setdefault('run', run)
        super().__init__(
            node=node,
            logger=logger,
            parent=run,
            skip_validation=skip_validation,
            raise_on_validation_error=raise_on_validation_error,
            **kwargs)

        # Check for possible remote plan reference first
        reference = self.node.get(['plan', 'import'])
        if reference is not None:
            self._remote_plan_fmf_id = FmfId.from_spec(reference)

        # Save the run, prepare worktree and plan data directory
        self.my_run = run
        self.worktree: Optional[Path] = None
        if self.my_run:
            # Skip to initialize the work tree if the corresponding option is
            # true. Note that 'tmt clean' consumes the option because it
            # should not initialize the work tree at all.
            if not self.my_run.opt(tmt.utils.PLAN_SKIP_WORKTREE_INIT):
                self._initialize_worktree()

            self._initialize_data_directory()

        # Store 'environment' and 'environment-file' keys content
        self._environment = self._get_environment_vars(node)
        # Expand all environment and context variables in the node
        with tmt.utils.modify_environ(self.environment):
            self._expand_node_data(node.data, {
                key: ','.join(value)
                for (key, value) in self._fmf_context.items()})

        # Initialize test steps
        self.discover = tmt.steps.discover.Discover(
            logger=logger.descend(logger_name='discover'),
            plan=self,
            data=self.node.get('discover')
            )
        self.provision = tmt.steps.provision.Provision(
            logger=logger.descend(logger_name='provision'),
            plan=self,
            data=self.node.get('provision')
            )
        self.prepare = tmt.steps.prepare.Prepare(
            logger=logger.descend(logger_name='prepare'),
            plan=self,
            data=self.node.get('prepare')
            )
        self.execute = tmt.steps.execute.Execute(
            logger=logger.descend(logger_name='execute'),
            plan=self,
            data=self.node.get('execute')
            )
        self.report = tmt.steps.report.Report(
            logger=logger.descend(logger_name='report'),
            plan=self,
            data=self.node.get('report')
            )
        self.finish = tmt.steps.finish.Finish(
            logger=logger.descend(logger_name='finish'),
            plan=self,
            data=self.node.get('finish')
            )

        self._update_metadata()

    def _expand_node_data(self, data: T, fmf_context: Dict[str, str]) -> T:
        """ Recursively expand variables in node data """
        if isinstance(data, str):
            # Expand environment and context variables. This is a bit
            # tricky as we do need to process each type individually and
            # also properly handle variable/context name conflicts and
            # situations when some variable is now known.

            # First split data per $ which to avoid conflicts.
            split_data = data.split('$')

            # Don't process the first item as that was not a variable.
            first_item = split_data.pop(0)

            # Do the environment variable expansion for items not
            # starting with @.
            expanded_env = [item if item.startswith('@')
                            else os.path.expandvars(f'${item}')
                            for item in split_data]

            # Do context expansion for items starting with $@ defining
            # environment variables using the fmf context dictionary.
            expanded_ctx = [first_item]
            with tmt.utils.modify_environ(fmf_context):
                for item in expanded_env:
                    if item.startswith('@'):
                        expanded = os.path.expandvars(f'${item[1:]}')
                        result = f'${item}' if expanded.startswith('$') else expanded
                    else:
                        result = item
                    expanded_ctx.append(result)

            # This cast is tricky: we get a string, and we return a
            # string, so T -> T hold, yet mypy does not recognize this,
            # and we need to help with an explicit cast().
            return cast(T, ''.join(expanded_ctx))

        if isinstance(data, dict):
            for key, value in data.items():
                data[key] = self._expand_node_data(value, fmf_context)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                data[i] = self._expand_node_data(item, fmf_context)
        return data

    # TODO: better, more elaborate ways of assigning serial numbers to tests
    # can be devised - starting with a really trivial one: each test gets
    # one, starting with `1`.
    #
    # For now, the test itself is not important, and it's part of the method
    # signature to leave the door open for more sophisticated methods that
    # might depend on the actual test properties. Our simple "increment by 1"
    # method does not need it.
    _test_serial_number_generator: Optional[Iterator[int]] = None

    def draw_test_serial_number(self, test: Test) -> int:
        if self._test_serial_number_generator is None:
            self._test_serial_number_generator = itertools.count(start=1, step=1)

        return next(self._test_serial_number_generator)

    @property
    def environment(self) -> EnvironmentType:
        """ Return combined environment from plan data and command line """
        if self.my_run:
            combined = self._environment.copy()
            # Command line variables take precedence
            combined.update(self.my_run.environment)
            # Include path to the plan data directory
            combined["TMT_PLAN_DATA"] = str(self.data_directory)
            # And tree path if possible
            if self.worktree:
                combined["TMT_TREE"] = str(self.worktree)

            return combined
        return self._environment

    def _get_environment_vars(self, node: fmf.Tree) -> EnvironmentType:
        """ Get variables from 'environment' and 'environment-file' keys """
        # Environment variables from files
        environment_files = node.get("environment-file") or []
        if not isinstance(environment_files, list):
            raise tmt.utils.NormalizationError(
                f'{self.name}:environment-file', environment_files, 'unset or a list of paths')
        combined = tmt.utils.environment_files_to_dict(
            filenames=environment_files,
            root=Path(node.root) if node.root else None,
            logger=self._logger)

        # Environment variables from key, make sure that values are string
        environment = {
            key: str(value) for key, value
            in node.get('environment', {}).items()}

        # Combine both sources into one ('environment' key takes precendence)
        combined.update(environment)
        return combined

    def _initialize_worktree(self) -> None:
        """
        Prepare the worktree, a copy of the metadata tree root

        Used as cwd in prepare, execute and finish steps.
        """

        # Do nothing for remote plan reference
        if self.is_remote_plan_reference:
            return

        # Prepare worktree path and detect the source tree root
        assert self.workdir is not None  # narrow type
        self.worktree = self.workdir / 'tree'
        tree_root = self.node.root

        # Create an empty directory if there's no metadata tree
        if not tree_root:
            self.debug('Create an empty worktree (no metadata tree).', level=2)
            self.worktree.mkdir(exist_ok=True)
            return

        # Sync metadata root to the worktree
        self.debug(f"Sync the worktree to '{self.worktree}'.", level=2)
        self.run(Command("rsync", "-ar", "--exclude", ".git", f"{tree_root}/", str(self.worktree)))

    def _initialize_data_directory(self) -> None:
        """
        Create the plan data directory

        This is used for storing logs and other artifacts created during
        prepare step, test execution or finish step and which are pulled
        from the guest for possible future inspection.
        """
        assert self.workdir is not None  # narrow type
        self.data_directory = self.workdir / "data"
        self.debug(
            f"Create the data directory '{self.data_directory}'.", level=2)
        self.data_directory.mkdir(exist_ok=True, parents=True)

    @property
    def _fmf_context(self) -> tmt.utils.FmfContext:
        """ Return combined context from plan data and command line """

        combined = FmfContext()

        combined.update(self.context)
        combined.update(self._cli_fmf_context)

        return combined

    @staticmethod
    def edit_template(raw_content: str) -> str:
        """ Edit the default template with custom values """

        content = tmt.utils.yaml_to_dict(raw_content)

        # For each step check for possible command line data
        for step in tmt.steps.STEPS:
            options = Plan._opt(step)
            if not options:
                continue
            # TODO: it'd be nice to annotate things here and there, template
            # is not a critical, let's go with Any for now
            step_data: Any = []

            # For each option check for valid yaml and store
            for option in options:
                try:
                    # FIXME: Ruamel.yaml "remembers" the used formatting when
                    #        using round-trip mode and since it comes from the
                    #        command-line, no formatting is applied resulting
                    #        in inconsistent formatting. Using a safe loader in
                    #        this case is a hack to make it forget, though
                    #        there may be a better way to do this.
                    try:
                        data = tmt.utils.yaml_to_dict(option, yaml_type='safe')
                        if not (data):
                            raise tmt.utils.GeneralError("Step data cannot be empty.")
                    except tmt.utils.GeneralError as error:
                        raise tmt.utils.GeneralError(
                            f"Invalid step data for {step}: '{option}'"
                            f"\n{error}")
                    step_data.append(data)
                except MarkedYAMLError as error:
                    raise tmt.utils.GeneralError(
                        f"Invalid yaml data for {step}:\n{error}")

            # Use list only when multiple step data provided
            if len(step_data) == 1:
                step_data = step_data[0]
            content[step] = step_data

        return tmt.utils.dict_to_yaml(content)

    @staticmethod
    def overview(tree: 'Tree') -> None:
        """ Show overview of available plans """
        plans = [
            style(str(plan), fg='red') for plan in tree.plans()]
        echo(style(
            'Found {}{}{}.'.format(
                listed(plans, 'plan'),
                ': ' if plans else '',
                listed(plans, max=12)
                ), fg='blue'))

    @staticmethod
    def create(
            *,
            name: str,
            template: str,
            path: Path,
            force: bool = False,
            dry: Optional[bool] = None,
            logger: tmt.log.Logger) -> None:
        """ Create a new plan """
        # Prepare paths
        if dry is None:
            dry = Plan._opt('dry')

        (directory, plan) = os.path.split(name)
        directory_path = path / directory.lstrip('/')
        has_fmf_ext = os.path.splitext(plan)[1] == '.fmf'
        plan_path = directory_path / (plan + ('' if has_fmf_ext else '.fmf'))

        # Create directory & plan
        tmt.utils.create_directory(
            path=directory_path,
            name='plan directory',
            dry=dry,
            logger=logger)
        try:
            content = tmt.templates.PLAN[template]
        except KeyError:
            raise tmt.utils.GeneralError(
                f"Invalid template '{template}'.")

        # Override template with data provided on command line
        content = Plan.edit_template(content)

        tmt.utils.create_file(
            path=plan_path, content=content,
            name='plan', dry=dry, force=force)

    def _iter_steps(self,
                    enabled: bool = True,
                    disabled: bool = False,
                    skip: Optional[List[str]] = None
                    ) -> Generator[Tuple[str, tmt.steps.Step], None, None]:
        """
        Iterate over enabled / all steps

        Yields instances of all enabled steps by default.
        Use 'disabled=True' to iterate over all.
        Use 'skip' to pass the list of steps to be skipped.
        """
        skip = skip or []
        for name in tmt.steps.STEPS:
            if name in skip:
                continue
            step = getattr(self, name)
            if (enabled and step.enabled or disabled and not step.enabled):
                yield (name, step)

    def steps(self, enabled: bool = True, disabled: bool = False,
              skip: Optional[List[str]] = None) -> Generator[tmt.steps.Step, None, None]:
        """
        Iterate over enabled / all steps

        Yields instances of all enabled steps by default.
        Use 'disabled=True' to iterate over all.
        Use 'skip' to pass the list of steps to be skipped.
        """
        for _, step in self._iter_steps(enabled=enabled, disabled=disabled, skip=skip):
            yield step

    def step_names(self, enabled: bool = True, disabled: bool = False,
                   skip: Optional[List[str]] = None) -> Generator[str, None, None]:
        """
        Iterate over enabled / all step names.

        Yields step names of all enabled steps by default.
        Use 'disabled=True' to iterate over all.
        Use 'skip' to pass the list of steps to be skipped.
        """
        for name, _ in self._iter_steps(enabled=enabled, disabled=disabled, skip=skip):
            yield name

    def show(self) -> None:
        """ Show plan details """

        # Summary and description first
        self.ls(summary=True)
        if self.description:
            echo(tmt.utils.format(
                'description', self.description, key_color='green'))

        # Individual step details
        for step in self.steps(disabled=True):
            step.show()

        # Environment and context
        if self.environment:
            echo(tmt.utils.format(
                'environment', self.environment, key_color='blue'))
        if self._fmf_context:
            echo(tmt.utils.format(
                'context', self._fmf_context, key_color='blue'))

        # The rest
        echo(tmt.utils.format('enabled', self.enabled, key_color='cyan'))
        if self.order != DEFAULT_ORDER:
            echo(tmt.utils.format('order', str(self.order), key_color='cyan'))
        if self.id:
            echo(tmt.utils.format('id', self.id, key_color='cyan'))
        if self.tag:
            echo(tmt.utils.format('tag', self.tag, key_color='cyan'))
        if self.tier:
            echo(tmt.utils.format('tier', self.tier, key_color='cyan'))
        if self.link is not None:
            self.link.show()
        if self.verbosity_level:
            self._show_additional_keys()

        # Show fmf id of the remote plan in verbose mode
        if (self._original_plan or self._remote_plan_fmf_id) and self.verbosity_level:
            # Pick fmf id from the original plan by default, use the
            # current plan in shallow mode when no plans are fetched.
            if self._original_plan is not None:
                fmf_id = self._original_plan._remote_plan_fmf_id
            else:
                fmf_id = self._remote_plan_fmf_id

            echo(tmt.utils.format('import', '', key_color='blue'))
            assert fmf_id is not None  # narrow type
            for key, value in fmf_id.items():
                echo(tmt.utils.format(key, value, key_color='green'))

    # FIXME - Make additional attributes configurable
    def lint_unknown_keys(self) -> LinterReturn:
        """ P001: all keys are known """

        invalid_keys = self._lint_keys(
            list(self.step_names(enabled=True, disabled=True)) + self._extra_l2_keys)

        if invalid_keys:
            for key in invalid_keys:
                yield LinterOutcome.FAIL, f'unknown key "{key}" is used'

            return

        yield LinterOutcome.PASS, 'correct keys are used'

    def lint_execute_not_defined(self) -> LinterReturn:
        """ P002: execute step must be defined with "how" """

        if not self.node.get('execute'):
            yield LinterOutcome.FAIL, 'execute step must be defined with "how"'
            return

        yield LinterOutcome.PASS, 'execute step defined with "how"'

    def _step_phase_nodes(self, step: str) -> List[Dict[str, Any]]:
        """ List raw fmf nodes for the given step """

        _phases = self.node.get(step)

        if not _phases:
            return []

        if isinstance(_phases, dict):
            return [_phases]

        return cast(List[Dict[str, Any]], _phases)

    def _lint_step_methods(
            self,
            step: str,
            plugin_class: Type[tmt.steps.BasePlugin]) -> LinterReturn:
        """ P003: execute step methods must be known """

        phases = self._step_phase_nodes(step)

        if not phases:
            yield LinterOutcome.SKIP, f'{step} step is not defined'
            return

        methods = [method.name for method in plugin_class.methods()]

        invalid_phases = [
            phase
            for phase in phases
            if phase.get('how') not in methods
            ]

        if invalid_phases:
            for phase in invalid_phases:
                yield LinterOutcome.FAIL, \
                    f'unknown {step} method "{phase.get("how")}" in "{phase.get("name")}"'

            return

        yield LinterOutcome.PASS, f'{step} step methods are all known'

    # TODO: can we use self.discover & its data instead? A question to be answered
    # by better schema & lint cooperation - e.g. unknown methods shall be reported
    # by schema-based validation already.
    def lint_execute_unknown_method(self) -> LinterReturn:
        """ P003: execute step methods must be known """

        yield from self._lint_step_methods('execute', tmt.steps.execute.ExecutePlugin)

    def lint_discover_unknown_method(self) -> LinterReturn:
        """ P004: discover step methods must be known """

        yield from self._lint_step_methods('discover', tmt.steps.discover.DiscoverPlugin)

    def lint_fmf_remote_ids_valid(self) -> LinterReturn:
        """ P005: remote fmf ids must be valid """

        fmf_ids: List[Tuple[FmfId, Dict[str, Any]]] = []

        for phase in self._step_phase_nodes('discover'):
            if phase.get('how') != 'fmf':
                continue

            # Skipping `name` on purpose - that belongs to the whole step,
            # it's not treated as part of fmf id.
            fmf_id_data = cast(
                _RawFmfId,
                {key: value for key, value in phase.items() if key in ['url', 'ref', 'path']}
                )

            if not fmf_id_data:
                continue

            fmf_ids.append((FmfId.from_spec(fmf_id_data), phase))

        if fmf_ids:
            for fmf_id, phase in fmf_ids:
                valid, error = fmf_id.validate()

                if valid:
                    yield LinterOutcome.PASS, f'remote fmf id in "{phase.get("name")}" is valid'

                else:
                    yield LinterOutcome.FAIL, \
                        f'remote fmf id in "{phase.get("name")}" is invalid, {error}'

            return

        yield LinterOutcome.SKIP, 'no remote fmf ids defined'

    def go(self) -> None:
        """ Execute the plan """
        # Show plan name and summary (one blank line to separate plans)
        self.info('')
        self.info(self.name, color='red')
        if self.summary:
            self.verbose('summary', self.summary, 'green')

        # Additional debug info like plan environment
        self.debug('info', color='cyan', shift=0, level=3)
        # TODO: something better than str()?
        self.debug('environment', str(self.environment), 'magenta', level=3)
        self.debug('context', str(self._fmf_context), 'magenta', level=3)

        # Wake up all steps
        self.debug('wake', color='cyan', shift=0, level=2)
        for step in self.steps(disabled=True):
            self.debug(str(step), color='blue', level=2)
            try:
                step.wake()
            except tmt.utils.SpecificationError as error:
                # Re-raise the exception if the step is enabled (invalid
                # step data), otherwise just warn the user and continue.
                if step.enabled:
                    raise error

                step.warn(str(error))

        # Set up login and reboot plugins for all steps
        self.debug("action", color="blue", level=2)
        for step in self.steps(disabled=True):
            step.setup_actions()

        # Check if steps are not in stand-alone mode
        standalone = set()
        for step in self.steps():
            standalone_plugins = step.plugins_in_standalone_mode
            if standalone_plugins == 1:
                standalone.add(step.name)
            elif standalone_plugins > 1:
                raise tmt.utils.GeneralError(
                    f"Step '{step.name}' has multiple plugin configs which "
                    f"require running on their own. Combination of such "
                    f"configs is not possible.")
        if len(standalone) > 1:
            raise tmt.utils.GeneralError(
                f'These steps require running on their own, their combination '
                f'with the given options is not compatible: '
                f'{fmf.utils.listed(standalone)}.')
        if standalone:
            assert self._cli_context_object is not None  # narrow type
            self._cli_context_object.steps = standalone
            self.debug(
                f"Running the '{list(standalone)[0]}' step as standalone.")

        # Run enabled steps except 'finish'
        self.debug('go', color='cyan', shift=0, level=2)
        abort = False
        try:
            for step in self.steps(skip=['finish']):
                step.go()
                # Finish plan if no tests found (except dry mode)
                if (isinstance(step, tmt.steps.discover.Discover) and not step.tests()
                        and not self.opt('dry')):
                    step.info(
                        'warning', 'No tests found, finishing plan.',
                        color='yellow', shift=1)
                    abort = True
                    return
        # Make sure we run 'finish' step always if enabled
        finally:
            if not abort and self.finish.enabled:
                self.finish.go()

    def _export(self, *, keys: Optional[List[str]] = None) -> tmt.export._RawExportedInstance:
        data = super()._export(keys=keys)

        # Maybe we could have some `export` callback in `field()`...
        data['context'] = data['context'].to_spec()

        for key in self._extra_l2_keys:
            value = self.node.data.get(key)
            if value:
                data[key] = value

        for step_name in tmt.steps.STEPS:
            step = cast(tmt.steps.Step, getattr(self, step_name))

            value = step._export()
            if value:
                data[step.step_name] = value

        return data

    @property
    def is_remote_plan_reference(self) -> bool:
        """ Check whether the plan is a remote plan reference """
        return self._remote_plan_fmf_id is not None

    def import_plan(self) -> Optional['Plan']:
        """ Import plan from a remote repository, return a Plan instance """
        if not self.is_remote_plan_reference:
            return None

        if self._imported_plan:
            return self._imported_plan

        assert self._remote_plan_fmf_id is not None  # narrow type
        plan_id = self._remote_plan_fmf_id
        self.debug(f"Import remote plan '{plan_id.name}' from '{plan_id.url}'.", level=3)

        # Clone the whole git repository if executing tests (run is attached)
        if self.my_run and not self.my_run.opt('dry'):
            assert self.parent is not None  # narrow type
            assert self.parent.workdir is not None  # narrow type
            destination = self.parent.workdir / "import" / self.name.lstrip("/")
            if plan_id.url is None:
                raise tmt.utils.SpecificationError(
                    f"No url provided for remote plan '{self.name}'.")
            if destination.exists():
                self.debug(f"Seems that '{destination}' has been already cloned.", level=3)
            else:
                tmt.utils.git_clone(plan_id.url, destination, self)
            if plan_id.ref:
                # Attempt to evaluate dynamic reference
                try:
                    dynamic_ref = resolve_dynamic_ref(
                        workdir=destination,
                        ref=plan_id.ref,
                        plan=self,
                        logger=self._logger
                        )
                    if plan_id.ref != dynamic_ref:
                        self.debug(f"Update 'ref' to '{dynamic_ref}'.")
                        plan_id.ref = dynamic_ref
                except tmt.utils.FileError as error:
                    raise tmt.utils.DiscoverError(
                        f"Failed to resolve dynamic ref of '{plan_id.ref}'.") from error
                if plan_id.ref:
                    self.run(Command('git', 'checkout', plan_id.ref), cwd=destination)
            if plan_id.path:
                destination = destination / plan_id.path.unrooted()
            node = fmf.Tree(str(destination)).find(plan_id.name)

        # Use fmf cache for exploring plans (the whole git repo is not needed)
        else:
            if str(plan_id.ref).startswith('@'):
                self.debug(f"Not enough data to evaluate dynamic ref '{plan_id.ref}', "
                           "going to clone the repository to read dynamic ref definition.")
                with tempfile.TemporaryDirectory() as tmpdirname:
                    git_clone(str(plan_id.url), Path(tmpdirname), self, None, shallow=True)
                    self.run(Command(
                        'git', 'checkout', 'HEAD', str(plan_id.ref)[1:]),
                        cwd=Path(tmpdirname))
                    # Attempt to evaluate dynamic reference
                    try:
                        dynamic_ref = resolve_dynamic_ref(
                            workdir=Path(tmpdirname),
                            ref=plan_id.ref,
                            plan=self,
                            logger=self._logger
                            )
                        if plan_id.ref != dynamic_ref:
                            self.debug(f"Update 'ref' to '{dynamic_ref}'.")
                            plan_id.ref = dynamic_ref
                    except tmt.utils.FileError as error:
                        raise tmt.utils.DiscoverError(
                            f"Failed to resolve dynamic ref of '{plan_id.ref}'.") from error
            try:
                node = fmf.Tree.node(plan_id.to_minimal_spec())
            except fmf.utils.FetchError as error:
                raise tmt.utils.GitUrlError(
                    f"Failed to import remote plan '{self.name}', "
                    f"use '--shallow' to skip cloning repositories.\n{error}")
        if not node:
            raise tmt.utils.DiscoverError(
                f"Failed to find plan '{plan_id.name}' "
                f"at 'url: {plan_id.url}, 'ref: {plan_id.ref}'.")
        # Override the plan name with the local one to ensure unique names
        node.name = self.name
        # Create the plan object, save links between both plans
        self._imported_plan = Plan(node=node, run=self.my_run, logger=self._logger.descend())
        self._imported_plan._original_plan = self

        # Update imported plan environment with the local environment
        self._imported_plan.environment.update(self.environment)
        with tmt.utils.modify_environ(self.environment):
            self._expand_node_data(node.data, {
                key: ','.join(value)
                for (key, value) in self._fmf_context.items()})

        return self._imported_plan

    def prune(self) -> None:
        """ Remove all uninteresting files from the plan workdir """

        logger = self._logger.descend(extra_shift=1)

        logger.verbose(
            f"Prune '{self.name}' plan workdir '{self.workdir}'.",
            color="magenta",
            level=3)

        if self.worktree:
            logger.debug(f"Prune '{self.name}' worktree '{self.worktree}'.", level=3)
            shutil.rmtree(self.worktree)

        for step in self.steps(disabled=True):
            step.prune(logger=step._logger)


class StoryPriority(enum.Enum):
    MUST_HAVE = 'must have'
    SHOULD_HAVE = 'should have'
    COULD_HAVE = 'could have'
    WILL_NOT_HAVE = 'will not have'

    # We need a custom "to string" conversion to support fmf's filter().
    def __str__(self) -> str:
        return self.value


@dataclasses.dataclass(repr=False)
class Story(
        Core,
        tmt.export.Exportable['Story'],
        tmt.lint.Lintable['Story']):
    """ User story object """

    example: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list)
    # TODO: `story` is mandatory, but it's defined after attributes with default
    # values. Try to find a way how to drop the need for a dummy default.
    story: Optional[str] = None
    title: Optional[str] = None
    priority: Optional[StoryPriority] = field(
        default=None,
        normalize=lambda key_address, raw_value, logger:
            None if raw_value is None else StoryPriority(raw_value))

    _KEYS_SHOW_ORDER = [
        'summary',
        'title',
        'story',
        'id',
        'priority',
        'description',
        'example',
        'enabled',
        'order',
        'tag',
        'tier',
        'link',
        ]

    def __init__(
            self,
            *,
            node: fmf.Tree,
            skip_validation: bool = False,
            raise_on_validation_error: bool = False,
            logger: tmt.log.Logger,
            **kwargs: Any) -> None:
        """ Initialize the story """
        super().__init__(node=node, logger=logger, skip_validation=skip_validation,
                         raise_on_validation_error=raise_on_validation_error, **kwargs)
        self._update_metadata()

    # Override the parent implementation - it would try to call `Tree.storys()`...
    @classmethod
    def from_tree(cls, tree: 'tmt.Tree') -> List['Story']:
        return tree.stories()

    def _export(self, *, keys: Optional[List[str]] = None) -> tmt.export._RawExportedInstance:
        data = super()._export(keys=keys)

        for key, value in data.items():
            if key == 'priority' and value is not None:
                data[key] = cast(StoryPriority, value).value

        return data

    @property
    def documented(self) -> List['Link']:
        """ Return links to relevant documentation """
        return self.link.get('documented-by') if self.link else []

    @property
    def verified(self) -> List['Link']:
        """ Return links to relevant test coverage """
        return self.link.get('verified-by') if self.link else []

    @property
    def implemented(self) -> List['Link']:
        """ Return links to relevant source code """
        return self.link.get('implemented-by') if self.link else []

    @property
    def status(self) -> List[str]:
        """ Aggregate story status from implemented-, verified- and documented-by links """
        status = []

        if self.implemented:
            status.append('implemented')

        if self.verified:
            status.append('verified')

        if self.documented:
            status.append('documented')

        return status

    def _match(
            self, implemented: bool, verified: bool, documented: bool, covered: bool,
            unimplemented: bool, unverified: bool, undocumented: bool, uncovered: bool) -> bool:
        """ Return true if story matches given conditions """
        if implemented and not self.implemented:
            return False
        if verified and not self.verified:
            return False
        if documented and not self.documented:
            return False
        if unimplemented and self.implemented:
            return False
        if unverified and self.verified:
            return False
        if undocumented and self.documented:
            return False
        if uncovered and (
                self.implemented and self.verified and self.documented):
            return False
        if covered and not (
                self.implemented and self.verified and self.documented):
            return False
        return True

    @staticmethod
    def create(
            *,
            name: str,
            template: str,
            path: Path,
            force: bool = False,
            dry: Optional[bool] = None,
            logger: tmt.log.Logger) -> None:
        """ Create a new story """
        if dry is None:
            dry = Story._opt('dry')

        # Prepare paths
        (directory, story) = os.path.split(name)
        directory_path = path / directory.lstrip('/')
        has_fmf_ext = os.path.splitext(story)[1] == '.fmf'
        story_path = directory_path / (story + ('' if has_fmf_ext else '.fmf'))

        # Create directory & story
        tmt.utils.create_directory(
            path=directory_path,
            name='story directory',
            dry=dry,
            logger=logger)
        try:
            content = tmt.templates.STORY[template]
        except KeyError:
            raise tmt.utils.GeneralError(
                f"Invalid template '{template}'.")

        tmt.utils.create_file(
            path=story_path, content=content,
            name='story', dry=dry, force=force)

    @staticmethod
    def overview(tree: 'Tree') -> None:
        """ Show overview of available stories """
        stories = [
            style(str(story), fg='red') for story in tree.stories()]
        echo(style(
            'Found {}{}{}.'.format(
                listed(stories, 'story'),
                ': ' if stories else '',
                listed(stories, max=12)
                ), fg='blue'))

    def show(self) -> None:
        """ Show story details """
        self.ls()
        for key in self._KEYS_SHOW_ORDER:
            value = getattr(self, key)
            if key == 'link':
                value.show()
                continue
            if key == 'priority' and value is not None:
                value = cast(StoryPriority, value).value
            if key == 'order' and value == DEFAULT_ORDER:
                continue
            if value is not None and value != []:
                wrap: tmt.utils.FormatWrap = False if key == 'example' else 'auto'
                echo(tmt.utils.format(key, value, wrap=wrap))
        if self.verbosity_level:
            self._show_additional_keys()

    def coverage(self, code: bool, test: bool, docs: bool) -> Tuple[bool, bool, bool]:
        """ Show story coverage """
        if code:
            code = bool(self.implemented)
            verdict(code, good='done ', bad='todo ', nl=False)
        if test:
            test = bool(self.verified)
            verdict(test, good='done ', bad='todo ', nl=False)
        if docs:
            docs = bool(self.documented)
            verdict(docs, good='done ', bad='todo ', nl=False)
        echo(self)
        return (code, test, docs)

    # FIXME - Make additional attributes configurable
    def lint_unknown_keys(self) -> LinterReturn:
        """ S001: all keys are known """

        invalid_keys = self._lint_keys(EXTRA_STORY_KEYS)

        if invalid_keys:
            for key in invalid_keys:
                yield LinterOutcome.FAIL, f'unknown key "{key}" is used'

            return

        yield LinterOutcome.PASS, 'correct keys are used'

    def lint_story(self) -> LinterReturn:
        """ S002: story key must be defined """

        if not self.node.get('story'):
            yield LinterOutcome.FAIL, 'story is required'
            return

        yield LinterOutcome.PASS, 'story key is defined'


Test.discover_linters()
Plan.discover_linters()
Story.discover_linters()


class Tree(tmt.utils.Common):
    """ Test Metadata Tree """

    def __init__(self,
                 *,
                 path: Optional[Path] = None,
                 tree: Optional[fmf.Tree] = None,
                 fmf_context: Optional[FmfContext] = None,
                 logger: tmt.log.Logger) -> None:
        """ Initialize tmt tree from directory path or given fmf tree """

        # TODO: not calling parent __init__ on purpose?
        self.inject_logger(logger)

        self._path = path or Path.cwd()
        self._tree = tree
        self._custom_fmf_context = fmf_context or FmfContext()

    @classmethod
    def grow(
            cls,
            *,
            path: Optional[Path] = None,
            tree: Optional[fmf.Tree] = None,
            fmf_context: Optional[FmfContext] = None,
            logger: Optional[tmt.log.Logger] = None) -> 'Tree':
        """
        Initialize tmt tree from directory path or given fmf tree.

        This method serves as an entry point for interactive use of
        tmt-as-a-library, providing sane defaults.

        .. warning::

           This method has a **very** limited use case, i.e. to help
           bootstrapping interactive tmt sessions. Using it anywhere
           outside of this scope should be ruled out.
        """

        import tmt.plugins

        logger = logger or tmt.log.Logger.create()

        tmt.plugins.explore(logger)

        return Tree(
            path=path or Path.cwd(),
            tree=tree,
            fmf_context=fmf_context,
            logger=logger or tmt.log.Logger.create())

    @property
    def _fmf_context(self) -> FmfContext:
        """ Use custom fmf context if provided, default otherwise """
        return self._custom_fmf_context or super()._fmf_context

    def _filters_conditions(
            self,
            nodes: Sequence[CoreT],
            filters: List[str],
            conditions: List[str],
            links: List['LinkNeedle'],
            excludes: List[str]) -> List[CoreT]:
        """ Apply filters and conditions, return pruned nodes """
        result = []
        for node in nodes:
            filter_vars = copy.deepcopy(node._metadata)
            cond_vars = node._metadata
            # Add a lowercase version of bool variables for filtering
            bool_vars = {
                key: [value, str(value).lower()]
                for key, value in filter_vars.items()
                if isinstance(value, bool)}
            filter_vars.update(bool_vars)
            # Conditions
            try:
                if not all(fmf.utils.evaluate(condition, cond_vars, node)
                           for condition in conditions):
                    continue
            except fmf.utils.FilterError:
                # Handle missing attributes as if condition failed
                continue
            except Exception as error:
                raise tmt.utils.GeneralError(
                    f"Invalid --condition raised exception: {error}")
            # Filters
            try:
                if not all(fmf.utils.filter(filter_, filter_vars, regexp=True)
                           for filter_ in filters):
                    continue
            except fmf.utils.FilterError:
                # Handle missing attributes as if filter failed
                continue
            # Links
            try:
                # Links are in OR relation
                if links and all(not node.has_link(needle) for needle in links):
                    continue
            except BaseException:
                # Handle broken link as not matching
                continue
            # Exclude
            if any(node for expr in excludes if re.search(expr, node.name)):
                continue
            result.append(node)
        return result

    def sanitize_cli_names(self, names: List[str]) -> List[str]:
        """ Sanitize CLI names in case name includes control character """
        for name in names:
            if not name.isprintable():
                raise tmt.utils.GeneralError(f"Invalid name {name!r} as it's not printable.")
        return names

    @property
    def tree(self) -> fmf.Tree:
        """ Initialize tree only when accessed """
        if self._tree is None:
            try:
                self._tree = fmf.Tree(str(self._path))
            except fmf.utils.RootError:
                raise tmt.utils.MetadataError(
                    f"No metadata found in the '{self._path}' directory. "
                    f"Use 'tmt init' to get started.")
            except fmf.utils.FileError as error:
                raise tmt.utils.GeneralError(f"Invalid yaml syntax: {error}")
            # Adjust metadata for current fmf context
            self._tree.adjust(fmf.context.Context(**self._fmf_context))
        return self._tree

    @tree.setter
    def tree(self, new_tree: fmf.Tree) -> None:
        self._tree = new_tree

    @property
    def root(self) -> Optional[Path]:
        """ Metadata root """
        if self.tree is None or self.tree.root is None:
            return None

        return Path(self.tree.root)

    def tests(
            self,
            logger: Optional[tmt.log.Logger] = None,
            keys: Optional[List[str]] = None,
            names: Optional[List[str]] = None,
            filters: Optional[List[str]] = None,
            conditions: Optional[List[str]] = None,
            unique: bool = True,
            links: Optional[List['LinkNeedle']] = None,
            excludes: Optional[List[str]] = None
            ) -> List[Test]:
        """ Search available tests """
        # Handle defaults, apply possible command line options
        logger = logger or self._logger
        keys = (keys or []) + ['test']
        names = names or []
        filters = (filters or []) + list(Test._opt('filters', []))
        conditions = (conditions or []) + list(Test._opt('conditions', []))
        # FIXME: cast() - typeless "dispatcher" method
        links = (links or []) + [
            LinkNeedle.from_spec(value)
            for value in cast(List[str], Test._opt('links', []))
            ]
        excludes = (excludes or []) + list(Test._opt('exclude', []))
        # Used in: tmt run test --name NAME, tmt test ls NAME...
        cmd_line_names: List[str] = list(Test._opt('names', []))

        # Sanitize test names to make sure no name includes control character
        cmd_line_names = self.sanitize_cli_names(cmd_line_names)

        def name_filter(nodes: Iterable[fmf.Tree]) -> List[fmf.Tree]:
            """ Filter nodes based on names provided on the command line """
            if not cmd_line_names:
                return list(nodes)
            return [
                node for node in nodes
                if any(re.search(name, node.name) for name in cmd_line_names)]

        # Append post filter to support option --enabled or --disabled
        if Test._opt('enabled'):
            filters.append('enabled:true')
        if Test._opt('disabled'):
            filters.append('enabled:false')

        if Test._opt('source'):
            tests = [
                Test(node=test, logger=self._logger.descend()) for test in self.tree.prune(
                    keys=keys, sources=cmd_line_names)]

        else:
            # First let's build the list of test objects based on keys & names.
            # If duplicate test names are allowed, match test name/regexp
            # one-by-one and preserve the order of tests within a plan.
            if not unique and names:
                tests = []
                for name in names:
                    selected_tests = [
                        Test(
                            node=test,
                            logger=logger.descend(
                                logger_name=test.get('name', None)
                                )  # .apply_verbosity_options(**self._options),
                            ) for test in name_filter(self.tree.prune(keys=keys, names=[name]))]
                    tests.extend(sorted(selected_tests, key=lambda test: test.order))
            # Otherwise just perform a regular key/name filtering
            else:
                selected_tests = [
                    Test(
                        node=test,
                        logger=logger.descend(
                            logger_name=test.get('name', None)
                            )  # .apply_verbosity_options(**self._options),
                        ) for test in name_filter(self.tree.prune(keys=keys, names=names))]
                tests = sorted(selected_tests, key=lambda test: test.order)

        # Apply filters & conditions
        return self._filters_conditions(
            tests, filters, conditions, links, excludes)

    def plans(
            self,
            logger: Optional[tmt.log.Logger] = None,
            keys: Optional[List[str]] = None,
            names: Optional[List[str]] = None,
            filters: Optional[List[str]] = None,
            conditions: Optional[List[str]] = None,
            run: Optional['Run'] = None,
            links: Optional[List['LinkNeedle']] = None,
            excludes: Optional[List[str]] = None
            ) -> List[Plan]:
        """ Search available plans """
        # Handle defaults, apply possible command line options
        logger = logger or (run._logger if run is not None else self._logger)
        local_plan_keys = (keys or []) + ['execute']
        remote_plan_keys = (keys or []) + ['plan']
        names = (names or []) + list(Plan._opt('names', []))
        filters = (filters or []) + list(Plan._opt('filters', []))
        conditions = (conditions or []) + list(Plan._opt('conditions', []))
        # FIXME: cast() - typeless "dispatcher" method
        links = (links or []) + [
            LinkNeedle.from_spec(value)
            for value in cast(List[str], Plan._opt('links', []))
            ]
        excludes = (excludes or []) + list(Plan._opt('exclude', []))

        # Sanitize plan names to make sure no name includes control character
        names = self.sanitize_cli_names(names)

        # Append post filter to support option --enabled or --disabled
        if Plan._opt('enabled'):
            filters.append('enabled:true')
        if Plan._opt('disabled'):
            filters.append('enabled:false')

        # For --source option use names as sources
        if Plan._opt('source'):
            sources = names
            names = None
        else:
            sources = None

        # Build the list, convert to objects, sort and filter
        plans = [
            Plan(
                node=plan,
                logger=logger.descend(
                    logger_name=plan.get('name', None),
                    extra_shift=0
                    ).apply_verbosity_options(**Plan._cli_options),
                run=run) for plan in [
                *
                self.tree.prune(
                    keys=local_plan_keys,
                    names=names,
                    sources=sources),
                *
                self.tree.prune(
                    keys=remote_plan_keys,
                    names=names,
                    sources=sources),
                ]]

        plans = self._filters_conditions(
            sorted(plans, key=lambda plan: plan.order),
            filters, conditions, links, excludes)
        if Plan._opt('shallow'):
            return plans
        return [plan.import_plan() or plan for plan in plans]

    def stories(
            self,
            logger: Optional[tmt.log.Logger] = None,
            keys: Optional[List[str]] = None,
            names: Optional[List[str]] = None,
            filters: Optional[List[str]] = None,
            conditions: Optional[List[str]] = None,
            whole: bool = False,
            links: Optional[List['LinkNeedle']] = None,
            excludes: Optional[List[str]] = None
            ) -> List[Story]:
        """ Search available stories """
        # Handle defaults, apply possible command line options
        logger = logger or self._logger
        keys = (keys or []) + ['story']
        names = (names or []) + list(Story._opt('names', []))
        filters = (filters or []) + list(Story._opt('filters', []))
        conditions = (conditions or []) + list(Story._opt('conditions', []))
        # FIXME: cast() - typeless "dispatcher" method
        links = (links or []) + [
            LinkNeedle.from_spec(value)
            for value in cast(List[str], Story._opt('links', []))
            ]
        excludes = (excludes or []) + list(Story._opt('exclude', []))

        # Sanitize story names to make sure no name includes control character
        names = self.sanitize_cli_names(names)

        # Append post filter to support option --enabled or --disabled
        if Story._opt('enabled'):
            filters.append('enabled:true')
        if Story._opt('disabled'):
            filters.append('enabled:false')

        # For --source option use names as sources
        if Story._opt('source'):
            sources = names
            names = None
        else:
            sources = None

        # Build the list, convert to objects, sort and filter
        stories = [
            Story(node=story, logger=logger.descend()) for story
            in self.tree.prune(keys=keys, names=names, whole=whole, sources=sources)]
        return self._filters_conditions(
            sorted(stories, key=lambda story: story.order),
            filters, conditions, links, excludes)

    @staticmethod
    def init(
            *,
            path: Path,
            template: str,
            force: bool,
            logger: tmt.log.Logger) -> None:
        """ Initialize a new tmt tree, optionally with a template """
        path = path.resolve()
        dry = Tree._opt('dry')

        # Check for existing tree
        tree: Optional[Tree] = None

        try:
            tree = Tree(logger=logger, path=path)
            # Are we creating a new tree under the existing one?
            assert tree is not None  # narrow type
            if path == tree.root:
                echo(f"Tree '{tree.root}' already exists.")
            else:
                # Are we creating a nested tree?
                echo(f"Path '{path}' already has a parent tree root '{tree.root}'.")
                if not force and not confirm("Do you really want to initialize a nested tree?"):
                    return
                tree = None
        except tmt.utils.GeneralError:
            tree = None

        # Create a new tree
        if tree is None:
            if dry:
                echo(f"Tree '{path}' would be initialized.")
            else:
                try:
                    fmf.Tree.init(path)
                    tree = Tree(logger=logger, path=path)
                    assert tree.root is not None  # narrow type
                    path = tree.root
                except fmf.utils.GeneralError as error:
                    raise tmt.utils.GeneralError(
                        f"Failed to initialize tree in '{path}': {error}")
                echo(f"Tree '{tree.root}' initialized.")

        # Populate the tree with example objects if requested
        if template == 'empty':
            choices = listed(tmt.templates.INIT_TEMPLATES, join='or')
            echo(
                f"To populate it with example content, "
                f"use --template with {choices}.")
        else:
            echo(f"Applying template '{template}'.")

        if template == 'mini':
            tmt.Plan.create(
                name='/plans/example',
                template='mini',
                path=path,
                force=force,
                dry=dry,
                logger=logger)
        elif template == 'base':
            tmt.Test.create(
                name='/tests/example',
                template='beakerlib',
                path=path,
                force=force,
                dry=dry,
                logger=logger)
            tmt.Plan.create(
                name='/plans/example',
                template='base',
                path=path,
                force=force,
                dry=dry,
                logger=logger)
        elif template == 'full':
            tmt.Test.create(
                name='/tests/example',
                template='shell',
                path=path,
                force=force,
                dry=dry,
                logger=logger)
            tmt.Plan.create(
                name='/plans/example',
                template='full',
                path=path,
                force=force,
                dry=dry,
                logger=logger)
            tmt.Story.create(
                name='/stories/example',
                template='full',
                path=path,
                force=force,
                dry=dry,
                logger=logger)


@dataclasses.dataclass
class RunData(tmt.utils.SerializableContainer):
    root: Optional[str]
    plans: Optional[List[str]]
    # TODO: this needs resolution - _context_object.steps is List[Step],
    # but stores as a List[str] in run.yaml...
    steps: List[str]
    environment: EnvironmentType
    remove: bool


class Run(tmt.utils.Common):
    """ Test run, a container of plans """

    tree: Optional[Tree]

    def __init__(self,
                 *,
                 id_: Optional[Path] = None,
                 tree: Optional[Tree] = None,
                 cli_context: Optional['tmt.cli.Context'] = None,
                 logger: tmt.log.Logger) -> None:
        """ Initialize tree, workdir and plans """
        # Use the last run id if requested
        self.config = tmt.utils.Config()
        if cli_context is not None:
            if cli_context.params.get('last'):
                id_ = self.config.last_run
                if id_ is None:
                    raise tmt.utils.GeneralError(
                        "No last run id found. Have you executed any run?")
            if cli_context.params.get('follow') and id_ is None:
                raise tmt.utils.GeneralError(
                    "Run id has to be specified in order to use --follow.")
        # Do not create workdir now, postpone it until later, as options
        # have not been processed yet and we do not want commands such as
        # tmt run discover --how fmf --help to create a new workdir.
        super().__init__(cli_context=cli_context, logger=logger)
        self._workdir_path: WorkdirArgumentType = id_ or True
        self._tree = tree
        self._plans: Optional[List[Plan]] = None
        self._environment_from_workdir: EnvironmentType = {}
        self._environment_from_options: Optional[EnvironmentType] = None
        self.remove = self.opt('remove')

    def _use_default_plan(self) -> None:
        """ Prepare metadata tree with only the default plan """
        default_plan = tmt.utils.yaml_to_dict(tmt.templates.DEFAULT_PLAN)
        # The default discover method for this case is 'shell'
        default_plan[tmt.templates.DEFAULT_PLAN_NAME]['discover']['how'] = 'shell'
        self.tree = tmt.Tree(logger=self._logger, tree=fmf.Tree(default_plan))
        self.debug("No metadata found, using the default plan.")

    def _save_tree(self, tree: Optional[Tree]) -> None:
        """ Save metadata tree, handle the default plan """
        default_plan = tmt.utils.yaml_to_dict(tmt.templates.DEFAULT_PLAN)
        try:
            self.tree = tree if tree else tmt.Tree(logger=self._logger, path=Path('.'))
            self.debug(f"Using tree '{self.tree.root}'.")
            # Clear the tree and insert default plan if requested
            if Plan._opt("default"):
                new_tree = fmf.Tree(default_plan)
                # Make sure the fmf root is set for both the default
                # plan (needed during the discover step) and the whole
                # tree (which is stored to 'run.yaml' during save()).
                new_tree.find(tmt.templates.DEFAULT_PLAN_NAME).root = self.tree.root
                new_tree.root = self.tree.root
                self.tree.tree = new_tree
                self.debug("Enforcing use of the default plan.")
            # Insert default plan if no plan detected. Check using
            # tree.prune() instead of self.tree.plans() to prevent
            # creating plan objects which leads to wrong expansion of
            # environment variables from the command line.
            if not (list(self.tree.tree.prune(keys=['execute'])) or
                    list(self.tree.tree.prune(keys=['plan']))):
                self.tree.tree.update(default_plan)
                self.debug("No plan found, adding the default plan.")
        # Create an empty default plan if no fmf metadata found
        except tmt.utils.MetadataError:
            self._use_default_plan()

    @property
    def environment(self) -> EnvironmentType:
        """ Return environment combined from wake up and command line """
        # Gather environment variables from options only once
        if self._environment_from_options is None:
            assert self.tree is not None  # narrow type
            self._environment_from_options = {}
            # Variables gathered from 'environment-file' options
            self._environment_from_options.update(
                tmt.utils.environment_files_to_dict(
                    filenames=(self.opt('environment-file') or []),
                    root=self.tree.root,
                    logger=self._logger))
            # Variables from 'environment' options (highest priority)
            self._environment_from_options.update(
                tmt.utils.environment_to_dict(
                    variables=self.opt('environment'), logger=self._logger))

        # Combine workdir and command line
        combined = self._environment_from_workdir.copy()
        combined.update(self._environment_from_options)
        return combined

    def save(self) -> None:
        """ Save list of selected plans and enabled steps """
        assert self.tree is not None  # narrow type
        assert self._cli_context_object is not None  # narrow type
        data = RunData(
            root=str(self.tree.root) if self.tree.root else None,
            plans=[plan.name for plan in self._plans] if self._plans is not None else None,
            steps=list(self._cli_context_object.steps),
            environment=self.environment,
            remove=self.remove
            )
        self.write(Path('run.yaml'), tmt.utils.dict_to_yaml(data.to_serialized()))

    def load_from_workdir(self) -> None:
        """
        Load the run from its workdir, do not require the root in
        run.yaml to exist. Doest not load the fmf tree.

        Use only when the data in workdir is sufficient (e.g. tmt
        clean and status only require the steps to be loaded and
        their status).
        """
        self._save_tree(self._tree)
        self._workdir_load(self._workdir_path)
        try:
            data = RunData.from_serialized(tmt.utils.yaml_to_dict(self.read(Path('run.yaml'))))
        except tmt.utils.FileError:
            self.debug('Run data not found.')
            return
        self._environment_from_workdir = data.environment
        assert self._cli_context_object is not None  # narrow type
        self._cli_context_object.steps = set(data.steps)

        self._plans = []

        # The root directory of the tree may not be available, create
        # an fmf node that only contains the necessary attributes
        # required for plan/step loading. We will also need a dummy
        # parent for these nodes, so we would correctly load each
        # plan's name.
        dummy_parent = fmf.Tree({'summary': 'unused'})

        for plan in (data.plans or []):
            node = fmf.Tree({'execute': None}, name=plan, parent=dummy_parent)
            self._plans.append(
                Plan(
                    node=node,
                    logger=self._logger.descend(),
                    run=self,
                    skip_validation=True))

    def load(self) -> None:
        """ Load list of selected plans and enabled steps """
        try:
            data = RunData.from_serialized(tmt.utils.yaml_to_dict(self.read(Path('run.yaml'))))
        except tmt.utils.FileError:
            self.debug('Run data not found.')
            return

        # If run id was given and root was not explicitly specified,
        # create a new Tree from the root in run.yaml
        if self._workdir and not self.opt('root'):
            if data.root:
                self._save_tree(tmt.Tree(logger=self._logger.descend(), path=Path(data.root)))
            else:
                # The run was used without any metadata, default plan
                # was used, load it
                self._use_default_plan()

        # Filter plans by name unless specified on the command line
        plan_options = ['names', 'filters', 'conditions', 'links', 'default']
        if not any(Plan._opt(option) for option in plan_options):
            assert self.tree is not None  # narrow type
            self._plans = [
                plan for plan in self.tree.plans(run=self)
                if data.plans and plan.name in data.plans]

        # Initialize steps only if not selected on the command line
        step_options = 'all since until after before skip'.split()
        selected = any(self.opt(option) for option in step_options)
        assert self._cli_context_object is not None  # narrow type
        if not selected and not self._cli_context_object.steps:
            self._cli_context_object.steps = set(data.steps)

        # Store loaded environment
        self._environment_from_workdir = data.environment
        self.debug(
            f"Loaded environment: '{self._environment_from_workdir}'.",
            level=3)

        # If the remove was enabled, restore it, option overrides
        self.remove = self.remove or data.remove
        self.debug(f"Remove workdir when finished: {self.remove}", level=3)

    @property
    def plans(self) -> List[Plan]:
        """ Test plans for execution """
        if self._plans is None:
            assert self.tree is not None  # narrow type
            self._plans = self.tree.plans(run=self, filters=['enabled:true'])
        return self._plans

    def finish(self) -> None:
        """ Check overall results, return appropriate exit code """
        # We get interesting results only if execute or prepare step is enabled
        execute = self.plans[0].execute
        report = self.plans[0].report
        interesting_results = execute.enabled or report.enabled

        # Gather all results and give an overall summary
        results = [
            result
            for plan in self.plans
            for result in plan.execute.results()]
        if interesting_results:
            self.info('')
            self.info('total', Result.summary(results), color='cyan')

        # Remove the workdir if enabled
        if self.remove and self.plans[0].finish.enabled:
            self._workdir_cleanup(self.workdir)

        # Skip handling of the exit codes in dry mode and
        # when there are no interesting results available
        if self.opt('dry') or not interesting_results:
            return

        # Return 0 if test execution has been intentionally skipped
        if tmt.steps.execute.Execute._opt("dry"):
            raise SystemExit(0)
        # Return appropriate exit code based on the total stats
        stats = Result.total(results)
        if sum(stats.values()) == 0:
            raise SystemExit(3)
        if stats[ResultOutcome.ERROR]:
            raise SystemExit(2)
        if stats[ResultOutcome.FAIL] + stats[ResultOutcome.WARN]:
            raise SystemExit(1)
        if stats[ResultOutcome.PASS]:
            raise SystemExit(0)
        raise SystemExit(2)

    def follow(self) -> None:
        """ Periodically check for new lines in the log. """
        assert self.workdir is not None  # narrow type
        with open(self.workdir / tmt.log.LOG_FILENAME) as logfile:
            # Move to the end of the file
            logfile.seek(0, os.SEEK_END)
            # Rewind some lines back to show more context
            location = logfile.tell()
            read_lines = 0
            while location >= 0:
                logfile.seek(location)
                location -= 1
                current_char = logfile.read(1)
                if current_char == '\n':
                    read_lines += 1
                if read_lines > FOLLOW_LINES:
                    break

        while True:
            line = logfile.readline()
            if line:
                print(line, end='')
            else:
                time.sleep(0.5)

    def go(self) -> None:
        """ Go and do test steps for selected plans """
        # Create the workdir and save last run
        self._save_tree(self._tree)
        self._workdir_load(self._workdir_path)
        assert self.tree is not None  # narrow type
        assert self._workdir is not None  # narrow type
        if self.tree.root and self._workdir.is_relative_to(self.tree.root):
            raise tmt.utils.GeneralError(
                f"Run workdir '{self._workdir}' must not be inside fmf root '{self.tree.root}'.")
        assert self.workdir is not None  # narrow type
        self.config.last_run = self.workdir
        # Show run id / workdir path
        self.info(str(self.workdir), color='magenta')
        self.debug(f"tmt version: {tmt.__version__}")
        self.debug('tmt command line', str(Command(*sys.argv)))
        # Attempt to load run data
        self.load()
        # Follow log instead of executing the run
        if self.opt('follow'):
            self.follow()

        # Propagate dry mode from provision to prepare, execute and finish
        # (basically nothing can be done if there is no guest provisioned)
        if tmt.steps.provision.Provision._opt("dry"):
            tmt.steps.prepare.Prepare._cli_options["dry"] = True
            tmt.steps.execute.Execute._cli_options["dry"] = True
            tmt.steps.finish.Finish._cli_options["dry"] = True

        # Enable selected steps
        assert self._cli_context_object is not None  # narrow type
        enabled_steps = self._cli_context_object.steps
        all_steps = self.opt('all') or not enabled_steps
        since = self.opt('since')
        until = self.opt('until')
        after = self.opt('after')
        before = self.opt('before')
        skip = self.opt('skip')

        if any([all_steps, since, until, after, before]):
            # Detect index of the first and last enabled step
            if since:
                first = tmt.steps.STEPS.index(since)
            elif after:
                first = tmt.steps.STEPS.index(after) + 1
            else:
                first = tmt.steps.STEPS.index('discover')
            if until:
                last = tmt.steps.STEPS.index(until)
            elif before:
                last = tmt.steps.STEPS.index(before) - 1
            else:
                last = tmt.steps.STEPS.index('finish')
            # Enable all steps between the first and last
            for index in range(first, last + 1):
                step = tmt.steps.STEPS[index]
                if step not in skip:
                    enabled_steps.add(step)
        self.debug(f"Enabled steps: {fmf.utils.listed(enabled_steps)}")

        # Show summary, store run data
        if not self.plans:
            raise tmt.utils.GeneralError("No plans found.")
        self.verbose(f"Found {listed(self.plans, 'plan')}.")
        self.save()

        # Iterate over plans
        crashed_plans: List[Tuple[Plan, Exception]] = []

        for plan in self.plans:
            try:
                plan.go()

            except Exception as exc:
                if self.opt('on-plan-error') == 'quit':
                    raise tmt.utils.GeneralError(
                        'plan failed',
                        causes=[exc])

                crashed_plans.append((plan, exc))

        if crashed_plans:
            raise tmt.utils.GeneralError(
                'plan failed',
                causes=[exc for _, exc in crashed_plans])

        # Update the last run id at the very end
        # (override possible runs created during execution)
        self.config.last_run = self.workdir

        # Give the final summary, remove workdir, handle exit codes
        self.finish()


class Status(tmt.utils.Common):
    """ Status of tmt work directories. """

    LONGEST_STEP = max(tmt.steps.STEPS, key=lambda k: len(k))
    FIRST_COL_LEN = len(LONGEST_STEP) + 2

    @staticmethod
    def get_overall_plan_status(plan: Plan) -> str:
        """ Examines the plan status (find the last done step) """
        steps = list(plan.steps())
        step_names = list(plan.step_names())
        for i in range(len(steps) - 1, -1, -1):
            if steps[i].status() == 'done':
                if i + 1 == len(steps):
                    # Last enabled step, consider the whole plan done
                    return 'done'
                return step_names[i]
        return 'todo'

    def plan_matches_filters(self, plan: Plan) -> bool:
        """ Check if the given plan matches filters from the command line """
        if self.opt('abandoned'):
            return (plan.provision.status() == 'done'
                    and plan.finish.status() == 'todo')
        if self.opt('active'):
            return any(step.status() == 'todo' for step in plan.steps())
        if self.opt('finished'):
            return all(step.status() == 'done' for step in plan.steps())
        return True

    @staticmethod
    def colorize_column(content: str) -> str:
        """ Add color to a status column """
        if 'done' in content:
            return style(content, fg='green')
        return style(content, fg='yellow')

    @classmethod
    def pad_with_spaces(cls, string: str) -> str:
        """ Append spaces to string to properly align the first column """
        return string + (cls.FIRST_COL_LEN - len(string)) * ' '

    def run_matches_filters(self, run: Run) -> bool:
        """ Check if the given run matches filters from the command line """
        if self.opt('abandoned') or self.opt('active'):
            # Any of the plans must be abandoned/active for the whole
            # run to be abandoned/active
            return any(self.plan_matches_filters(p) for p in run.plans)
        if self.opt('finished'):
            # All plans must be finished for the whole run to be finished
            return all(self.plan_matches_filters(p) for p in run.plans)
        return True

    def print_run_status(self, run: Run) -> None:
        """ Display the overall status of the run """
        if not self.run_matches_filters(run):
            return
        # Find the earliest step in all plans' status
        earliest_step_index = len(tmt.steps.STEPS)
        for plan in run.plans:
            plan_status = self.get_overall_plan_status(plan)
            if plan_status == 'done':
                continue
            if plan_status == 'todo':
                # If plan has no steps done, consider the whole run not done
                earliest_step_index = -1
                break
            plan_status_index = tmt.steps.STEPS.index(plan_status)
            if plan_status_index < earliest_step_index:
                earliest_step_index = plan_status_index

        if earliest_step_index == len(tmt.steps.STEPS):
            run_status = 'done'
        elif earliest_step_index == -1:
            run_status = 'todo'
        else:
            run_status = tmt.steps.STEPS[earliest_step_index]
        run_status = self.colorize_column(self.pad_with_spaces(run_status))
        echo(run_status, nl=False)
        echo(run.workdir)

    def print_plans_status(self, run: Run) -> None:
        """ Display the status of each plan of the given run """
        for plan in run.plans:
            if self.plan_matches_filters(plan):
                plan_status = self.get_overall_plan_status(plan)
                echo(self.colorize_column(self.pad_with_spaces(plan_status)),
                     nl=False)
                echo(f'{run.workdir}  {plan.name}')

    def print_verbose_status(self, run: Run) -> None:
        """ Display the status of each step of the given run """
        for plan in run.plans:
            if self.plan_matches_filters(plan):
                for step in plan.steps(disabled=True):
                    column = (step.status() or '----') + ' '
                    echo(self.colorize_column(column), nl=False)
                echo(f' {run.workdir}  {plan.name}')

    def process_run(self, run: Run) -> None:
        """ Display the status of the given run based on verbosity """
        loaded, error = tmt.utils.load_run(run)
        if not loaded:
            self.warn(f"Failed to load run '{run.workdir}': {error}")
            return
        if self.verbosity_level == 0:
            self.print_run_status(run)
        elif self.verbosity_level == 1:
            self.print_plans_status(run)
        else:
            self.print_verbose_status(run)

    def print_header(self) -> None:
        """ Print the header of the status table based on verbosity """
        header = ''
        if self.verbosity_level >= 2:
            for step in tmt.steps.STEPS:
                header += (step[0:4] + ' ')
            header += ' '
        else:
            header = self.pad_with_spaces('status')
        header += 'id'
        echo(style(header, fg='blue'))

    def show(self) -> None:
        """ Display the current status """
        # Prepare absolute workdir path if --id was used
        # FIXME: cast() - typeless "dispatcher" method
        id_ = cast(str, self.opt('id'))
        root_path = Path(self.opt('workdir-root'))
        self.print_header()
        assert self._cli_context_object is not None  # narrow type
        assert self._cli_context_object.tree is not None  # narrow type
        for abs_path in tmt.utils.generate_runs(root_path, id_):
            run = Run(
                logger=self._logger,
                id_=abs_path,
                tree=self._cli_context_object.tree,
                cli_context=self._cli_context)
            self.process_run(run)


CleanCallback = Callable[[], bool]


class Clean(tmt.utils.Common):
    """ A class for cleaning up workdirs, guests or images """

    def __init__(self,
                 *,
                 parent: Optional[tmt.utils.Common] = None,
                 name: Optional[str] = None,
                 workdir: tmt.utils.WorkdirArgumentType = None,
                 cli_context: Optional['tmt.cli.Context'] = None,
                 logger: tmt.log.Logger) -> None:
        """
        Initialize name and relation with the parent object

        Always skip to initialize the work tree.
        """
        # Set the option to skip to initialize the work tree
        if cli_context:
            cli_context.params[tmt.utils.PLAN_SKIP_WORKTREE_INIT] = True
        super().__init__(
            logger=logger,
            parent=parent,
            name=name,
            workdir=workdir,
            cli_context=cli_context)

    def images(self) -> bool:
        """ Clean images of provision plugins """
        self.info('images', color='blue')
        successful = True
        for method in tmt.steps.provision.ProvisionPlugin.methods():
            # FIXME: ignore[union-attr]: https://github.com/teemtee/tmt/issues/1599
            if not method.class_.clean_images(self, self.opt('dry')):  # type: ignore[union-attr]
                successful = False
        return successful

    def _matches_how(self, plan: Plan) -> bool:
        """ Check if the given plan matches options """
        how = plan.provision.data[0].how
        # FIXME: cast() - typeless "dispatcher" method
        target_how = cast(Optional[str], self.opt('how'))
        if target_how:
            return how == target_how
        # No target provision method, always matches
        return True

    def _stop_running_guests(self, run: Run) -> bool:
        """ Stop all running guests of a run """
        loaded, error = tmt.utils.load_run(run)
        if not loaded:
            self.warn(f"Failed to load run '{run.workdir}': {error}")
            return False
        # Clean guests if provision is done but finish is not done
        successful = True
        for plan in run.plans:
            if plan.provision.status() == 'done' and plan.finish.status() != 'done':
                # Wake up provision to load the active guests
                plan.provision.wake()
                if not self._matches_how(plan):
                    continue
                if self.opt('dry'):
                    self.verbose(
                        f"Would stop guests in run '{run.workdir}'"
                        f" plan '{plan.name}'.", shift=1)
                else:
                    self.verbose(f"Stopping guests in run '{run.workdir}' "
                                 f"plan '{plan.name}'.", shift=1)
                    # Set --quiet to avoid finish logging to terminal

                    quiet = self._cli_options['quiet']
                    self._cli_options['quiet'] = True
                    try:
                        plan.finish.go()
                    except tmt.utils.GeneralError as error:
                        self.warn(f"Could not stop guest in run "
                                  f"'{run.workdir}': {error}.", shift=1)
                        successful = False
                    finally:
                        self._cli_options['quiet'] = quiet
        return successful

    def guests(self) -> bool:
        """ Clean guests of runs """
        self.info('guests', color='blue')
        root_path = Path(self.opt('workdir-root'))
        # FIXME: cast() - typeless "dispatcher" method
        id_ = cast(str, self.opt('id_'))
        if self.opt('last'):
            # Pass the context containing --last to Run to choose
            # the correct one.
            return self._stop_running_guests(
                Run(logger=self._logger, cli_context=self._cli_context))
        successful = True
        assert self._cli_context_object is not None  # narrow type
        for abs_path in tmt.utils.generate_runs(root_path, id_):
            run = Run(
                logger=self._logger,
                id_=abs_path,
                tree=self._cli_context_object.tree,
                cli_context=self._cli_context)
            if not self._stop_running_guests(run):
                successful = False
        return successful

    def _clean_workdir(self, path: Path) -> bool:
        """ Remove a workdir (unless in dry mode) """
        if self.opt('dry'):
            self.verbose(f"Would remove workdir '{path}'.", shift=1)
        else:
            self.verbose(f"Removing workdir '{path}'.", shift=1)
            try:
                shutil.rmtree(path)
            except OSError as error:
                self.warn(f"Failed to remove '{path}': {error}.", shift=1)
                return False
        return True

    def runs(self) -> bool:
        """ Clean workdirs of runs """
        self.info('runs', color='blue')
        root_path = Path(self.opt('workdir-root'))
        # FIXME: cast() - typeless "dispatcher" method
        id_ = cast(str, self.opt('id_'))
        if self.opt('last'):
            # Pass the context containing --last to Run to choose
            # the correct one.
            last_run = Run(logger=self._logger, cli_context=self._cli_context)
            last_run._workdir_load(last_run._workdir_path)
            assert last_run.workdir is not None  # narrow type
            return self._clean_workdir(last_run.workdir)
        all_workdirs = list(tmt.utils.generate_runs(root_path, id_))
        keep = self.opt('keep')
        if keep is not None:
            # Sort by modify time of the workdirs and keep the newest workdirs
            all_workdirs.sort(
                key=lambda workdir: os.path.getmtime(workdir / 'run.yaml'), reverse=True)
            all_workdirs = all_workdirs[keep:]

        successful = True
        for workdir in all_workdirs:
            if not self._clean_workdir(workdir):
                successful = False

        return successful


@dataclasses.dataclass
class LinkNeedle:
    """
    A container to use for searching links.

    ``relation`` and ``target`` fields hold regular expressions that
    are to be searched for in the corresponding fields of :py:class:`Link`
    instances.
    """

    relation: str = r'.*'
    target: str = r'.*'

    @classmethod
    def from_spec(cls, value: str) -> 'LinkNeedle':
        """
        Convert from a specification file or from a CLI option

        Specification is described in [1], this constructor takes care
        of parsing it into a corresponding ``LinkNeedle`` instance.

        [1] https://tmt.readthedocs.io/en/stable/spec/plans.html#fmf
        """

        parts = value.split(':', maxsplit=1)

        if len(parts) == 1:
            return LinkNeedle(target=parts[0])

        return LinkNeedle(relation=parts[0], target=parts[1])

    def __str__(self) -> str:
        return f'{self.relation}:{self.target}'

    def matches(self, link: 'Link') -> bool:
        """ Find out whether a given link matches this needle """

        # Rule out the simple case, mismatching relation.
        if not re.search(self.relation, link.relation):
            return False

        # If the target is a string, the test is trivial.
        if isinstance(link.target, str):
            return re.search(self.target, link.target) is not None

        # If the target is an fmf id, the current basic implementation will
        # check just the `name` key, if it's defined. More fields may come
        # later, pending support for more sophisticated parsing of link
        # needle on a command line.
        if link.target.name:
            return re.search(self.target, link.target.name) is not None

        return False


@dataclasses.dataclass
class Link(tmt.utils.SpecBasedContainer[Any, _RawLinkRelation]):
    """
    An internal "link" as defined by tmt specification.

    All links, after entering tmt internals, are converted from their raw
    representation into instances of this class.

    [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
    """

    DEFAULT_RELATIONSHIP: ClassVar[_RawLinkRelationName] = 'relates'

    relation: _RawLinkRelationName
    target: Union[str, FmfId]
    note: Optional[str] = None

    @classmethod
    def from_spec(cls, spec: _RawLink) -> 'Link':
        """
        Convert from a specification file or from a CLI option

        Specification is described in [1], this constructor takes care
        of parsing it into a corresponding ``Link`` instance.

        [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
        """

        # `spec` can be either a string, fmf id, or relation:target mapping with
        # a single key (modulo `note` key, of course).

        # String is simple: if `spec` is a string, it represents a target,
        # and we use the default relationship.
        if isinstance(spec, str):
            return Link(relation=Link.DEFAULT_RELATIONSHIP, target=spec)

        # From now on, `spec` is a mapping, and may contain the optional
        # `note` key. Extract the key for later.
        # FIXME: cast() - typeless "dispatcher" method
        note = cast(Optional[str], spec.get('note', None))

        # Count how many relations are stored in spec.
        relations = [cast(_RawLinkRelationName, key)
                     for key in spec if key not in ([*FmfId.VALID_KEYS, 'note'])]

        # If there are no relations, spec must be an fmf id, representing
        # a target.
        if len(relations) == 0:
            return Link(
                relation=Link.DEFAULT_RELATIONSHIP,
                target=FmfId.from_spec(cast(_RawFmfId, spec)),
                note=note)

        # More relations than 1 are a hard error, only 1 is allowed.
        if len(relations) > 1:
            raise tmt.utils.SpecificationError(
                f"Multiple relations specified for the link "
                f"({fmf.utils.listed(relations)}).")

        # At this point, we know there's just a single relation, its value is the target,
        # and note we already put aside.
        #
        # ignore[typeddict-item]: as far as mypy knows, we did not narrow the type of `spec`,
        # _RawFmfId is still in play - but we do know it's no longer possible because such a
        # value we ruled out thanks to `"no relations" check above. At this point,
        # the right side of relation must be _RawLinkTarget and nothing else. Helping
        # mypy to realize that.
        relation = relations[0]
        raw_target = cast(_RawLinkTarget, spec[relation])  # type: ignore[typeddict-item]

        # TODO: this should not happen with mandatory validation
        if relation not in Links._relations:
            raise tmt.utils.SpecificationError(
                f"Invalid link relation '{relation}' (should be "
                f"{fmf.utils.listed(Links._relations, join='or')}).")

        if isinstance(raw_target, str):
            return Link(relation=relation, target=raw_target, note=note)

        return Link(relation=relation, target=FmfId.from_spec(raw_target), note=note)

    def to_spec(self) -> _RawLinkRelation:
        """
        Convert to a form suitable for saving in a specification file

        No matter what the original specification was, every link will
        generate the very same type of specification, the ``relation: target``
        one.

        Output of this method is fully compatible with specification, and when
        given to :py:meth:`from_spec`, it shall create a ``Link`` instance
        with the same properties as the original one.

        [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
        """

        spec: _RawLinkRelation = {
            self.relation: self.target.to_spec() if isinstance(
                self.target,
                FmfId) else self.target}

        if self.note is not None:
            spec['note'] = self.note

        return spec


class Links(tmt.utils.SpecBasedContainer[Any, List[_RawLinkRelation]]):
    """
    Collection of links in tests, plans and stories.

    Provides abstraction over the whole collection of object's links.

    [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
    """

    # The list of all supported link relations
    _relations: List[_RawLinkRelationName] = [
        'verifies', 'verified-by',
        'implements', 'implemented-by',
        'documents', 'documented-by',
        'blocks', 'blocked-by',
        'duplicates', 'duplicated-by',
        'parent', 'child',
        'relates', 'test-script',
        ]

    _links: List[Link]

    def __init__(self, *, data: Optional[_RawLinks] = None):
        """ Create a collection from raw link data """

        # TODO: this should not happen with mandatory validation
        if data is not None and not isinstance(data, (str, dict, list)):
            # TODO: deliver better key address, needs to know the parent
            raise tmt.utils.NormalizationError(
                'link', data, 'a string, a fmf id or a list of their combinations')

        # Nothing to do if no data provided
        if data is None:
            self._links = []

            return

        specs = data if isinstance(data, list) else [data]

        # Ensure that each link is in the canonical form
        self._links = [Link.from_spec(spec) for spec in specs]

    def to_spec(self) -> List[_RawLinkRelation]:
        """
        Convert to a form suitable for saving in a specification file

        No matter what the original specification was, every link will
        generate the very same type of specification, the ``relation: target``
        one.

        Output of this method is fully compatible with specification, and when
        used to instantiate :py:meth:`Link` object, it shall create a collection
        of links with the same properties as the original one.

        [1] https://tmt.readthedocs.io/en/stable/spec/core.html#link
        """

        return [
            link.to_spec()
            for link in self._links
            ]

    def get(self, relation: Optional[_RawLinkRelationName] = None) -> List[Link]:
        """ Get links with given relation, all by default """
        return [
            link for link in self._links
            if relation is None or link.relation == relation]

    def show(self) -> None:
        """ Format a list of links with their relations """
        for link in self._links:
            # TODO: needs a format for fmf id target
            echo(tmt.utils.format(
                link.relation.rstrip('-by'), f"{link.target}", key_color='cyan', wrap=False))

    def has_link(self, needle: Optional[LinkNeedle] = None) -> bool:
        """
        Check whether this set of links contains a matching link.

        If ``needle`` is left unspecified, method would take all links into
        account, as if the ``needle`` was match all possible links (``.*:.*``).
        Method would then answer the question "are there *any* links at all?"

        :param needle: if set, only links matching ``needle`` are considered. If
            not set, method considers all present links.
        :returns: ``True`` if there are matching links, ``False`` otherwise.
        """

        if needle is None:
            return bool(self._links)

        return any(needle.matches(link) for link in self._links)

    def __bool__(self) -> bool:
        return self.has_link()


def resolve_dynamic_ref(
        *,
        workdir: Path,
        ref: Optional[str],
        plan: Plan,
        logger: tmt.log.Logger) -> Optional[str]:
    """
    Get the final value for the dynamic reference

    Returns original ref if the dynamic referencing isn't used.
    Plan is used for context and environment expansion to process reference.
    Common instance is used for appropriate logging.
    """

    # Nothing to do if no dynamic reference provided
    if not ref or not ref.startswith("@"):
        return ref

    # Prepare path of the dynamic reference file
    ref_filepath = workdir / ref[1:]
    if not ref_filepath.exists():
        raise tmt.utils.FileError(
            f"Dynamic 'ref' definition file '{ref_filepath}' does not exist.")
    logger.debug(f"Dynamic 'ref' definition file '{ref_filepath}' detected.")

    # Read it, process it and get the value of the attribute 'ref'
    try:
        with open(ref_filepath, encoding='utf-8') as datafile:
            data = tmt.utils.yaml_to_dict(datafile.read())
    except OSError as error:
        raise tmt.utils.FileError(f"Failed to read '{ref_filepath}'.") from error
    # Build a dynamic reference tree, adjust ref based on the context
    reference_tree = fmf.Tree(data=data)
    reference_tree.adjust(fmf.context.Context(**plan._fmf_context))
    # Also temporarily build a plan so that env and context variables are expanded
    Plan(logger=logger, node=reference_tree, run=plan.my_run, skip_validation=True)
    ref = reference_tree.get("ref")

    # RET504: Unnecessary variable assignment before `return` statement. Keeping for readability.
    return ref  # noqa: RET504
