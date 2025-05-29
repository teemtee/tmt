"""
Container decorators and helpers.
"""

import dataclasses
import functools
import inspect
import textwrap
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, TypeVar, Union, cast, overload

import fmf

from tmt._compat.pydantic import BaseModel, Extra, Field, ValidationError
from tmt._compat.typing import Self

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    import tmt.log
    import tmt.options
    from tmt._compat.typing import TypeAlias


# A stand-in variable for generic use.
T = TypeVar('T')

# According to [1], this is the easiest way how to notify type checker
# `container` is an alias for `dataclass`. Assignment is not recognized
# by neither mypy nor pyright.
#
# There is also PEP681 and `dataclass_transform`, see [2], and when we
# switch to
#
# [1] https://github.com/python/mypy/issues/5383#issuecomment-1691288663
# [2] https://typing.readthedocs.io/en/latest/spec/dataclasses.html#dataclass-transform
from dataclasses import dataclass as container  # noqa: TID251,E402

# Importing the original dataclass `field` too. Be aware that this is
# not the end, eventually we will need a field representing metadata key,
# and a field for common containers. It will take a couple of patches to
# put things in the right slots. Maybe `simple_field` will be `field`,
# and `field` would become `metadata_field`, to align them more with
# their use cases.
from dataclasses import field as simple_field  # noqa: TID251, E402

#: Type of field's normalization callback.
NormalizeCallback: 'TypeAlias' = Callable[[str, Any, 'tmt.log.Logger'], T]

#: Type of field's exporter callback.
FieldExporter: 'TypeAlias' = Callable[[T], Any]

#: Type of field's CLI option specification.
FieldCLIOption: 'TypeAlias' = Union[str, Sequence[str]]

#: Type of field's serialization callback.
SerializeCallback: 'TypeAlias' = Callable[[T], Any]

#: Type of field's unserialization callback.
UnserializeCallback: 'TypeAlias' = Callable[[Any], T]

#: Types for generic "data container" classes and instances. In tmt code, this
#: reduces to data classes and data class instances. Our :py:class:`DataContainer`
#: are perfectly compatible data classes, but some helper methods may be used
#: on raw data classes, not just on ``DataContainer`` instances.
ContainerClass: 'TypeAlias' = type['DataclassInstance']
ContainerInstance: 'TypeAlias' = 'DataclassInstance'
Container: 'TypeAlias' = Union[ContainerClass, ContainerInstance]


def key_to_option(key: str) -> str:
    """
    Convert a key name to corresponding option name
    """

    return key.replace('_', '-')


def option_to_key(option: str) -> str:
    """
    Convert an option name to corresponding key name
    """

    return option.replace('-', '_')


@container
class FieldMetadata(Generic[T]):
    """
    A dataclass metadata container used by our custom dataclass field management.

    Attached to fields defined with :py:func:`field`
    """

    internal: bool = False

    #: Help text documenting the field.
    help: Optional[str] = None

    #: Specific values that should be shown in the documentation as
    #: interesting examples of the field usage.
    help_example_values: list[str] = simple_field(default_factory=list[str])

    #: If field accepts a value, this string would represent it in documentation.
    #: This stores the metavar provided when field was created - it may be unset.
    #: py:attr:`metavar` provides the actual metavar to be used.
    _metavar: Optional[str] = None

    #: The default value for the field.
    default: Optional[T] = None

    #: A zero-argument callable that will be called when a default value is
    #: needed for the field.
    default_factory: Optional[Callable[[], T]] = None

    #: Marks the fields as a flag.
    is_flag: bool = False

    #: Marks the field as accepting multiple values. When used on command line,
    #: the option could be used multiple times, accumulating values.
    multiple: bool = False

    #: If set, show the default value in command line help.
    show_default: bool = False

    #: Either a list of allowed values the field can take, or a zero-argument
    #: callable that would return such a list.
    _choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None

    #: Environment variable providing value for the field.
    envvar: Optional[str] = None

    #: Mark the option as deprecated. Instance of :py:class:`Deprecated`
    #: describes the version in which the field was deprecated plus an optional
    #: hint with the recommended alternative. Documentation and help texts would
    #: contain this info.
    deprecated: Optional['tmt.options.Deprecated'] = None

    #: One or more command-line option names.
    cli_option: Optional[FieldCLIOption] = None

    #: A normalization callback to call when loading the value from key source
    #: (performed by :py:class:`NormalizeKeysMixin`).
    normalize_callback: Optional['NormalizeCallback[T]'] = None

    # Callbacks for custom serialize/unserialize operations (performed by
    # :py:class:`SerializableContainer`).
    serialize_callback: Optional['SerializeCallback[T]'] = None
    unserialize_callback: Optional['SerializeCallback[T]'] = None

    #: An export callback to call when exporting the field (performed by
    #: :py:class:`tmt.export.Exportable`).
    export_callback: Optional['FieldExporter[T]'] = None

    #: CLI option parameters, for lazy option creation.
    _option_args: Optional['FieldCLIOption'] = None
    _option_kwargs: dict[str, Any] = simple_field(default_factory=dict[str, Any])

    #: A :py:func:`click.option` decorator defining a corresponding CLI option.
    _option: Optional['tmt.options.ClickOptionDecoratorType'] = None

    @functools.cached_property
    def choices(self) -> Optional[Sequence[str]]:
        """
        A list of allowed values the field can take
        """

        if isinstance(self._choices, (list, tuple)):
            return list(cast(Sequence[str], self._choices))

        if callable(self._choices):
            return self._choices()

        return None

    @functools.cached_property
    def metavar(self) -> Optional[str]:
        """
        Placeholder for field's value in documentation and help
        """

        if self._metavar:
            return self._metavar

        if self.choices:
            return '|'.join(self.choices)

        return None

    @property
    def has_default(self) -> bool:
        """
        Whether the field has a default value
        """

        return self.default_factory is not None or self.default is not dataclasses.MISSING

    @property
    def materialized_default(self) -> Optional[T]:
        """
        Returns the actual default value of the field
        """

        if self.default_factory is not None:
            return self.default_factory()

        if self.default is not dataclasses.MISSING:
            return self.default

        return None

    @property
    def option(self) -> Optional['tmt.options.ClickOptionDecoratorType']:
        if self._option is None and self.cli_option:
            from tmt.options import option

            self._option_args = (
                (self.cli_option,) if isinstance(self.cli_option, str) else self.cli_option
            )

            self._option_kwargs.update(
                {
                    'is_flag': self.is_flag,
                    'multiple': self.multiple,
                    'envvar': self.envvar,
                    'metavar': self.metavar,
                    'choices': self.choices,
                    'show_default': self.show_default,
                    'help': self.help,
                    'deprecated': self.deprecated,
                }
            )

            if self.default is not dataclasses.MISSING and not self.is_flag:
                self._option_kwargs['default'] = self.default

            self._option = option(*self._option_args, **self._option_kwargs)

        return self._option


def container_fields(container: Container) -> Iterator[dataclasses.Field[Any]]:
    yield from dataclasses.fields(container)


def container_has_field(container: Container, key: str) -> bool:
    return key in list(container_keys(container))


def container_keys(container: Container) -> Iterator[str]:
    """
    Iterate over key names in a container
    """

    for field in container_fields(container):
        yield field.name


def container_values(container: ContainerInstance) -> Iterator[Any]:
    """
    Iterate over values in a container
    """

    for field in container_fields(container):
        yield container.__dict__[field.name]


def container_items(container: ContainerInstance) -> Iterator[tuple[str, Any]]:
    """
    Iterate over key/value pairs in a container
    """

    for field in container_fields(container):
        yield field.name, container.__dict__[field.name]


def container_field(
    container: Container, key: str
) -> tuple[str, str, Any, dataclasses.Field[Any], 'FieldMetadata[Any]']:
    """
    Return a dataclass/data container field info by the field's name.

    Surprisingly, :py:mod:`dataclasses` package does not have a helper for
    this. One can iterate over fields, but there's no *public* API for
    retrieving a field when one knows its name.

    :param cls: a dataclass/data container class whose fields to search.
    :param key: field name to retrieve.
    :raises GeneralError: when the field does not exist.
    """
    import tmt.utils

    for field in container_fields(container):
        if field.name != key:
            continue

        metadata = cast(
            FieldMetadata[Any],
            field.metadata.get(
                'tmt',
                cast(FieldMetadata[Any], FieldMetadata()),  # type: ignore[redundant-cast]
            ),
        )

        return (
            field.name,
            key_to_option(field.name),
            container.__dict__[field.name] if not inspect.isclass(container) else None,
            field,
            metadata,
        )

    if isinstance(container, DataContainer):
        raise tmt.utils.GeneralError(
            f"Could not find field '{key}' in class '{container.__class__.__name__}'."
        )

    raise tmt.utils.GeneralError(f"Could not find field '{key}' in class '{container}'.")


@container
class DataContainer:
    """
    A base class for objects that have keys and values
    """

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to a mapping.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.
        """

        return dict(self.items())

    def to_minimal_dict(self) -> dict[str, Any]:
        """
        Convert to a mapping with unset keys omitted.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.
        """

        return {key: value for key, value in self.items() if value is not None}

    # This method should remain a class-method: 1. list of keys is known
    # already, therefore it's not necessary to create an instance, and
    # 2. some functionality makes use of this knowledge.
    @classmethod
    def keys(cls) -> Iterator[str]:
        """
        Iterate over key names
        """

        yield from container_keys(cls)

    def values(self) -> Iterator[Any]:
        """
        Iterate over key values
        """

        yield from container_values(self)

    def items(self) -> Iterator[tuple[str, Any]]:
        """
        Iterate over key/value pairs
        """

        yield from container_items(self)

    @classmethod
    def _default(cls, key: str, default: Any = None) -> Any:
        """
        Return a default value for a given key.

        Keys may have a default value, or a default *factory* has been specified.

        :param key: key to look for.
        :param default: when key has no default value, ``default`` is returned.
        :returns: a default value defined for the key, or its ``default_factory``'s
            return value of ``default_factory``, or ``default`` when key has no
            default value.
        """

        for field in container_fields(cls):
            if key != field.name:
                continue

            if not isinstance(field.default_factory, dataclasses._MISSING_TYPE):
                return field.default_factory()

            if not isinstance(field.default, dataclasses._MISSING_TYPE):
                return field.default

        else:
            return default

    @property
    def is_bare(self) -> bool:
        """
        Check whether all keys are either unset or have their default value.

        :returns: ``True`` if all keys either hold their default value
            or are not set at all, ``False`` otherwise.
        """

        for field in container_fields(self):
            value = getattr(self, field.name)

            if not isinstance(field.default_factory, dataclasses._MISSING_TYPE):
                if value != field.default_factory():
                    return False

            elif not isinstance(field.default, dataclasses._MISSING_TYPE):
                if value != field.default:
                    return False

            else:
                pass

        return True


#: A typevar bound to spec-based container base class. A stand-in for all classes
#: derived from :py:class:`SpecBasedContainer`.
SpecBasedContainerT = TypeVar(
    'SpecBasedContainerT',
    # ignore[type-arg]: generic bounds are not supported by mypy.
    bound='SpecBasedContainer',  # type: ignore[type-arg]
)

# It may look weird, having two different typevars for "spec", but it does make
# sense: tmt is fairly open to what it accepts, e.g. "a string or a list of
# strings". This is the input part of the flow. But then the input is normalized,
# and the output may be just a subset of types tmt is willing to accept. For
# example, if `tag` can be either a string or a list of strings, when processed
# by tmt and converted back to spec, a list of strings is the only output, even
# if the original was a single string. Therefore `SpecBasedContainer` accepts
# two types, one for each direction. Usually, the output one would be a subset
# of the input one.

#: A typevar representing an *input* specification consumed by :py:class:`SpecBasedContainer`.
SpecInT = TypeVar('SpecInT')
#: A typevar representing an *output* specification produced by :py:class:`SpecBasedContainer`.
SpecOutT = TypeVar('SpecOutT')


@container
class SpecBasedContainer(Generic[SpecInT, SpecOutT], DataContainer):
    @classmethod
    def from_spec(cls, spec: SpecInT) -> Self:
        """
        Convert from a specification file or from a CLI option

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`to_spec` for its counterpart.
        """

        raise NotImplementedError

    def to_spec(self) -> SpecOutT:
        """
        Convert to a form suitable for saving in a specification file

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`from_spec` for its counterpart.
        """

        return cast(SpecOutT, self.to_dict())

    def to_minimal_spec(self) -> SpecOutT:
        """
        Convert to specification, skip default values

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`from_spec` for its counterpart.
        """

        return cast(SpecOutT, self.to_minimal_dict())


SerializableContainerDerivedType = TypeVar(
    'SerializableContainerDerivedType', bound='SerializableContainer'
)


@container
class SerializableContainer(DataContainer):
    """
    A mixin class for saving and loading objects
    """

    @classmethod
    def default(cls, key: str, default: Any = None) -> Any:
        return cls._default(key, default=default)

    #
    # Moving data between containers and objects owning them
    #

    def inject_to(self, obj: Any) -> None:
        """
        Inject keys from this container into attributes of a given object
        """

        for name, value in self.items():
            setattr(obj, name, value)

    @classmethod
    def extract_from(cls, obj: Any) -> Self:
        """
        Extract keys from given object, and save them in a container
        """

        data = cls()
        # SIM118: Use `{key} in {dict}` instead of `{key} in {dict}.keys()`
        # "NormalizeKeysMixin" has no attribute "__iter__" (not iterable)
        for key in cls.keys():  # noqa: SIM118
            value = getattr(obj, key)
            if value is not None:
                setattr(data, key, value)

        return data

    #
    # Serialization - writing containers into YAML files, and restoring
    # them later.
    #

    def to_serialized(self) -> dict[str, Any]:
        """
        Convert to a form suitable for saving in a file.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`from_serialized` for its counterpart.
        """

        def _produce_serialized() -> Iterator[tuple[str, Any]]:
            for key in container_keys(self):
                _, option, value, _, metadata = container_field(self, key)

                if metadata.serialize_callback:
                    yield option, metadata.serialize_callback(value)

                else:
                    yield option, value

        serialized = dict(_produce_serialized())

        # Add a special field tracking what class we just shattered to pieces.
        serialized['__class__'] = {
            'module': self.__class__.__module__,
            'name': self.__class__.__name__,
        }

        return serialized

    @classmethod
    def from_serialized(cls, serialized: dict[str, Any]) -> Self:
        """
        Convert from a serialized form loaded from a file.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`to_serialized` for its counterpart.
        """

        # Our special key may or may not be present, depending on who
        # calls this method.  In any case, it is not needed, because we
        # already know what class to restore: this one.
        serialized.pop('__class__', None)

        def _produce_unserialized() -> Iterator[tuple[str, Any]]:
            for option, value in serialized.items():
                key = option_to_key(option)

                _, _, _, _, metadata = container_field(cls, key)

                if metadata.unserialize_callback:
                    yield key, metadata.unserialize_callback(value)

                else:
                    yield key, value

        # Set attribute by adding it to __dict__ directly. Messing with setattr()
        # might cause reuse of mutable values by other instances.
        # obj.__dict__[keyname] = unserialize_callback(value)

        return cls(**dict(_produce_unserialized()))

    @classmethod
    def unserialize_class(cls) -> Any:
        """
        Provide the actual class to unserialize.

        In some situations, the class recorded in the serialized state
        cannot be safely unserialized. Such classes may reimplement this
        method, and return the right class.
        """

        return cls

    # ignore[misc,type-var]: mypy is correct here, method does return a
    # TypeVar, but there is no way to deduce the actual type, because
    # the method is static. That's on purpose, method tries to find the
    # class to unserialize, therefore it's simply unknown. Returning Any
    # would make mypy happy, but we do know the return value will be
    # derived from SerializableContainer. We can mention that, and
    # silence mypy about the missing actual type.
    @staticmethod
    def unserialize(
        serialized: dict[str, Any], logger: 'tmt.log.Logger'
    ) -> SerializableContainerDerivedType:  # type: ignore[misc,type-var]
        """
        Convert from a serialized form loaded from a file.

        Similar to :py:meth:`from_serialized`, but this method knows
        nothing about container's class, and will locate the correct
        module and class by inspecting serialized data. Discovered
        class' :py:meth:`from_serialized` is then used to create the
        container.

        Used to transform data read from a YAML file into original
        containers when their classes are not know to the code.
        Restoring such containers requires inspection of serialized data
        and dynamic imports of modules as needed.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`to_serialized` for its counterpart.
        """

        import tmt.utils
        from tmt.plugins import import_member

        # Unpack class info, to get nicer variable names
        if "__class__" not in serialized:
            raise tmt.utils.GeneralError(
                "Failed to load saved state, probably because of old data format.\n"
                "Use 'tmt clean runs' to clean up old runs."
            )

        klass_info = serialized.pop('__class__')
        klass = import_member(
            module=klass_info['module'],
            member=klass_info['name'],
            logger=logger,
        )[1]

        # Stay away from classes that are not derived from this one, to
        # honor promise given by return value annotation.
        assert issubclass(klass, SerializableContainer)

        klass = klass.unserialize_class()

        assert issubclass(klass, SerializableContainer)

        # Apparently, the issubclass() check above is not good enough for mypy.
        return cast(SerializableContainerDerivedType, klass.from_serialized(serialized))


@overload
def field(
    *,
    default: bool,
    # Options
    option: Optional[FieldCLIOption] = None,
    is_flag: bool = True,
    choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
    multiple: bool = False,
    metavar: Optional[str] = None,
    envvar: Optional[str] = None,
    deprecated: Optional['tmt.options.Deprecated'] = None,
    help: Optional[str] = None,
    help_example_values: Optional[list[str]] = None,
    show_default: bool = False,
    internal: bool = False,
    # Input data normalization - not needed, the field is a boolean
    # flag.
    # normalize: Optional[NormalizeCallback[T]] = None
    # Custom serialization
    # serialize: Optional[SerializeCallback[bool]] = None,
    # unserialize: Optional[UnserializeCallback[bool]] = None
    # Custom exporter
    # exporter: Optional[FieldExporter[T]] = None
) -> bool:
    pass


@overload
def field(
    *,
    default: T,
    # Options
    option: Optional[FieldCLIOption] = None,
    is_flag: bool = False,
    choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
    multiple: bool = False,
    metavar: Optional[str] = None,
    envvar: Optional[str] = None,
    deprecated: Optional['tmt.options.Deprecated'] = None,
    help: Optional[str] = None,
    help_example_values: Optional[list[str]] = None,
    show_default: bool = False,
    internal: bool = False,
    # Input data normalization
    normalize: Optional[NormalizeCallback[T]] = None,
    # Custom serialization
    serialize: Optional[SerializeCallback[T]] = None,
    unserialize: Optional[UnserializeCallback[T]] = None,
    # Custom exporter
    exporter: Optional[FieldExporter[T]] = None,
) -> T:
    pass


@overload
def field(
    *,
    default_factory: Callable[[], T],
    # Options
    option: Optional[FieldCLIOption] = None,
    is_flag: bool = False,
    choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
    multiple: bool = False,
    metavar: Optional[str] = None,
    envvar: Optional[str] = None,
    deprecated: Optional['tmt.options.Deprecated'] = None,
    help: Optional[str] = None,
    help_example_values: Optional[list[str]] = None,
    show_default: bool = False,
    internal: bool = False,
    # Input data normalization
    normalize: Optional[NormalizeCallback[T]] = None,
    # Custom serialization
    serialize: Optional[SerializeCallback[T]] = None,
    unserialize: Optional[UnserializeCallback[T]] = None,
    # Custom exporter
    exporter: Optional[FieldExporter[T]] = None,
) -> T:
    pass


@overload
def field(
    *,
    # Options
    option: Optional[FieldCLIOption] = None,
    is_flag: bool = False,
    choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
    multiple: bool = False,
    metavar: Optional[str] = None,
    envvar: Optional[str] = None,
    deprecated: Optional['tmt.options.Deprecated'] = None,
    help: Optional[str] = None,
    help_example_values: Optional[list[str]] = None,
    show_default: bool = False,
    internal: bool = False,
    # Input data normalization
    normalize: Optional[NormalizeCallback[T]] = None,
    # Custom serialization
    serialize: Optional[SerializeCallback[T]] = None,
    unserialize: Optional[UnserializeCallback[T]] = None,
    # Custom exporter
    exporter: Optional[FieldExporter[T]] = None,
) -> T:
    pass


def field(
    *,
    default: Any = dataclasses.MISSING,
    default_factory: Any = None,
    # Options
    option: Optional[FieldCLIOption] = None,
    is_flag: bool = False,
    choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
    multiple: bool = False,
    metavar: Optional[str] = None,
    envvar: Optional[str] = None,
    deprecated: Optional['tmt.options.Deprecated'] = None,
    help: Optional[str] = None,
    help_example_values: Optional[list[str]] = None,
    show_default: bool = False,
    internal: bool = False,
    # Input data normalization
    normalize: Optional[NormalizeCallback[T]] = None,
    # Custom serialization
    serialize: Optional[SerializeCallback[T]] = None,
    unserialize: Optional[UnserializeCallback[T]] = None,
    # Custom exporter
    exporter: Optional[FieldExporter[T]] = None,
) -> Any:
    """
    Define a :py:class:`DataContainer` field.

    Effectively a fancy wrapper over :py:func:`dataclasses.field`, tailored for
    tmt code needs and simplification of various common tasks.

    :param default: if provided, this will be the default value for this field.
        Passed directly to :py:func:`dataclass.field`.
        It is an error to specify both ``default`` and ``default_factory``.
    :param default_factory: if provided, it must be a zero-argument callable
        that will be called when a default value is needed for this field.
        Passed directly to :py:func:`dataclass.field`.
        It is an error to specify both ``default`` and ``default_factory``.
    :param option: one or more command-line option names.
        Passed directly to :py:func:`click.option`.
    :param is_flag: marks this option as a flag.
        Passed directly to :py:func:`click.option`.
    :param choices: if provided, the command-line option would accept only
        the listed input values.
        Passed to :py:func:`click.option` as a :py:class:`click.Choice` instance.
    :param multiple: accept multiple arguments of the same name.
        Passed directly to :py:func:`click.option`.
    :param metavar: how the input value is represented in the help page.
        Passed directly to :py:func:`click.option`.
    :param envvar: environment variable used for this option.
        Passed directly to :py:func:`click.option`.
    :param deprecated: mark the option as deprecated
        Provide an instance of Deprecated() with version in which the
        option was obsoleted and an optional hint with the recommended
        alternative. A warning message will be added to the option help.
    :param help: the help string for the command-line option. Multiline strings
        can be used, :py:func:`textwrap.dedent` is applied before passing
        ``help`` to :py:func:`click.option`.
    :param help_example_values: Specific values that should be shown in
        the documentation as interesting examples of the field usage.
    :param show_default: show default value
        Passed directly to :py:func:`click.option`.
    :param internal: if set, the field is treated as internal-only, and will not
        appear when showing objects via ``show()`` method, or in export created
        by :py:meth:`Core._export`.
    :param normalize: a callback for normalizing the input value. Consumed by
        :py:class:`NormalizeKeysMixin`.
    :param serialize: a callback for custom serialization of the field value.
        Consumed by :py:class:`SerializableKeysMixin`.
    :param unserialize: a callback for custom unserialization of the field value.
        Consumed by :py:class:`SerializableKeysMixin`.
    :param exporter: a callback for custom export of the field value.
        Consumed by :py:class:`tmt.export.Exportable`.
    """
    import tmt.utils

    if option:
        if is_flag is False and isinstance(default, bool):
            raise tmt.utils.GeneralError(
                "Container field must be a flag to have boolean default value."
            )

        if is_flag is True and not isinstance(default, bool):
            raise tmt.utils.GeneralError(
                "Container field must have a boolean default value when it is a flag."
            )

    # ignore[arg-type]: returning "wrong" type on purpose. field() must be annotated
    # as if returning the value of type matching the field declaration, and the original
    # field() is called with wider argument types than expected, because we use our own
    # overloading to narrow types *our* custom field() accepts.
    # ignore[reportArgumentType]: not sure why these pop up, but `bool` keeps appearing
    # in the type of `default` value, and I was unable to sort things out in a way which
    # would make the `T` match.
    return simple_field(
        default=default,
        default_factory=default_factory or dataclasses.MISSING,  # type: ignore[arg-type]
        metadata={
            'tmt': FieldMetadata(
                internal=internal,
                help=textwrap.dedent(help).strip() if help else None,
                help_example_values=help_example_values
                if help_example_values is not None
                else list[str](),
                _metavar=metavar,
                default=default,
                default_factory=default_factory,
                show_default=show_default,
                is_flag=is_flag,
                multiple=multiple,
                _choices=choices,
                envvar=envvar,
                deprecated=deprecated,
                cli_option=option,
                normalize_callback=normalize,
                serialize_callback=serialize,  # type: ignore[reportArgumentType,unused-ignore]
                unserialize_callback=unserialize,
                export_callback=exporter,  # type: ignore[reportArgumentType,unused-ignore]
            )
        },
    )


#
# A base class for containers holding tmt metadata, content of fmf trees
# of various kinds.
#
# Note: this is a work in progress! We would like to reduce the amount
# of custom code implementing validation, normalization and srialization,
# and use existing and well-equipped libraries like attrs and Pydantic.
# Not all containers are converted, not all features are ready, do not
# be surprised if there are containers still using `DataContainer`
# family of classes.
#

#: A typevar bound to spec-based container base class. A stand-in for all classes
#: derived from :py:class:`SpecBasedContainer`.
MetadataContainerT = TypeVar(
    'MetadataContainerT',
    bound='MetadataContainer',
)

metadata_field = Field


class MetadataContainer(BaseModel):
    """
    A base class of containers backed by fmf nodes.
    """

    class Config:
        # Accept only keys with dashes instead of underscores
        alias_generator = key_to_option
        extra = Extra.forbid
        validate_all = True
        validate_assignment = True

    @classmethod
    def from_fmf(cls, tree: fmf.Tree) -> Self:
        try:
            return cls.parse_obj(tree.data)

        except ValidationError as error:
            import tmt.utils

            raise tmt.utils.SpecificationError(f"Invalid metadata in '{tree.name}'.") from error

    @classmethod
    def from_yaml(cls, yaml: str) -> Self:
        import tmt.utils

        try:
            return cls.parse_obj(tmt.utils.yaml_to_dict(yaml))

        except ValidationError as error:
            import tmt.utils

            raise tmt.utils.SpecificationError("Invalid metadata in YAML data.") from error
