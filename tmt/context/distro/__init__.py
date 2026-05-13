import abc
import re
from typing import ClassVar, Literal, Optional, Union

from fmf.context import CannotDecide

from tmt.container import container
from tmt.context import ContextError, TmtContextDimension, provides_context
from tmt.plugins import PluginRegistry as PluginRegistry


@container
class Version:
    """
    Distro version defining comparisons
    """

    parts: tuple[int, ...]

    def __str__(self) -> str:
        return ".".join([*(str(p) for p in self.parts)])

    @classmethod
    def from_str(cls, raw: str) -> Optional["Version"]:
        try:
            parts = tuple(int(p) for p in raw.split("."))
        except ValueError:
            return None
        return cls(parts)

    def _compare_version(self, other: "Version", minor_mode: bool = False) -> Literal[-1, 0, 1]:
        """
        Main comparison logic for different versions

        :arg other: the other version to compare to
        :arg minor_mode: whether to compare within the same major version
        :return:
          - 1 if this version is greater than the ``other``
          - 0 if this version is equal to the ``other``
          - -1 if this version is less than the ``other``
        :raises CannotDecide: when comparison is not supported
        """
        if minor_mode and len(self.parts) < len(other.parts):
            raise CannotDecide(
                f"Version '{self}' does not have enough parts to minor-mode compare to '{other}'"
            )
        if minor_mode:
            major_parts = len(other.parts) - 1
            # Compare the major parts. When there are no major parts, e.g. `9`, this
            # compares 2 empty tuples and falls through to the normal comparison mode
            if self.parts[:major_parts] != other.parts[:major_parts]:
                raise CannotDecide(
                    f"Versions '{self}' and '{other}' have mismatched major components"
                )

        # Get the significant bits
        part_to_compare = 1
        while self.parts[:part_to_compare] == other.parts[:part_to_compare]:
            # Check if we ran out of significant parts to compare
            if len(other.parts) == part_to_compare:
                break
            part_to_compare += 1

        # Checking equality we must limit to the significant bits,
        # otherwise tuple comparison fails when there are different number of parts
        if self.parts[:part_to_compare] == other.parts[:part_to_compare]:
            return 0
        # Here we can just use the `>` comparison of tuples which works for different lengths
        if self.parts > other.parts:
            return 1
        return -1


FALLBACK_DISTRO_PATTERN = re.compile(r"^(?P<id>[a-z]+)-?(?P<version>[\d.]*)$")

SANITIZE_DISTRO = re.compile(r"[^a-z\d.]+")


def sanitize_distro_name(raw_name: str) -> str:
    """
    Convert the distro name to lower case and replace any separators to ``-``.
    """
    return SANITIZE_DISTRO.sub("-", raw_name.lower())


@container
class Distro(abc.ABC):
    """
    Wrapper around distro and distro aliases defining comparisons.
    """

    #: Raw value used to construct the
    _raw_value: str

    #: Distro's ``ID``. See ``/etc/os-release``.
    id: str

    #: Distro's version number, name or alias.
    #: The comparison of non-semver alias must be defined in the ordering operators.
    version: Optional[Union[str, Version]] = None

    #: Registrar to identify the :py:class:`Distro` from supported regex patterns.
    _registrar: ClassVar[dict[re.Pattern[str], type["Distro"]]] = {}

    #: The regex pattern that identifies this distro
    _DISTRO_PATTERN: ClassVar[re.Pattern[str]]

    def __str__(self) -> str:
        return self._raw_value

    @classmethod
    @abc.abstractmethod
    def _create_distro(cls, raw_id: str, match: re.Match[str]) -> "Distro":
        """
        Actual constructor
        """
        raise NotImplementedError

    def _assert_compatible_distro(self, other: "Distro") -> None:
        """
        Check if other distro is compatible for comparison

        :raises CannotDecide: if distros cannot be compared to each other
        """
        if self.id != other.id:
            raise CannotDecide(f"Cannot compare distro '{self}' with '{other}'")

    def _compare_version(self, other: "Distro", minor_mode: bool = False) -> Literal[-1, 0, 1]:
        """
        Main comparison logic for different distro versions

        The base implementation does not support non-:py:class:`Version` comparisons. This must
        be defined by overriding this function.

        :arg other: the other distro to compare to
        :arg minor_mode: whether to compare within the same major version
        :return:
          - 1 if this version is greater than the ``other``
          - 0 if this version is equal to the ``other``
          - -1 if this version is less than the ``other``
        :raises CannotDecide: when comparison is not supported
        """
        assert self.version  # narrow type
        assert other.version  # narrow type
        if isinstance(self.version, str) or isinstance(other.version, str):
            raise CannotDecide
        return self.version._compare_version(other.version, minor_mode=minor_mode)

    def _eq_unversioned(self, other: "Distro") -> bool:
        """
        Check equality against another distro ID
        """
        assert not other.version  # narrow type
        # By default, the `_assert_compatible_distro` ensures we have the same id,
        # so we know that at this point the distros are equal
        return True

    def _op_eq(self, other: "Distro", minor_mode: bool = False) -> bool:
        self._assert_compatible_distro(other)
        # Comparator does not care what the main object's version is
        if not other.version:
            return self._eq_unversioned(other)
        # The main object does not have a specific version, we cannot compare
        if not self.version:
            raise CannotDecide(
                f"Distro '{self}' does not have a version to compare with '{other}'"
            )
        return self._compare_version(other, minor_mode=minor_mode) == 0

    def _op_greater(self, other: "Distro", minor_mode: bool = False) -> bool:
        self._assert_compatible_distro(other)
        # Either comparator or main object does not have a version
        if not self.version or not other.version:
            raise CannotDecide(
                f"Distro '{self}' does not have a version to compare with '{other}'"
            )
        return self._compare_version(other, minor_mode=minor_mode) == 1

    @classmethod
    def create(cls, raw_id: str) -> "Distro":
        """
        Generic constructor
        """
        id_sanitized = sanitize_distro_name(raw_id)
        for pattern, distro_cls in cls._registrar.items():
            if match := pattern.match(id_sanitized):
                return distro_cls._create_distro(id_sanitized, match)
        if not (match := FALLBACK_DISTRO_PATTERN.match(id_sanitized)):
            raise ContextError(f"Could not parse '{raw_id}' as a distro")
        raw_version = match.group("version")
        version = Version.from_str(raw_version) or raw_version or None
        return UnknownDistro(
            _raw_value=raw_id,
            id=match.group("id"),
            version=version,
        )

    @classmethod
    def __init_subclass__(cls) -> None:
        if hasattr(cls, "_DISTRO_PATTERN"):
            cls._registrar[cls._DISTRO_PATTERN] = cls


@container
class UnknownDistro(Distro):
    """
    Fallback distro if no registered distro matched.
    """

    @classmethod
    def _create_distro(cls, raw_id: str, match: re.Match[str]) -> "Distro":
        raise AssertionError("UnknownDistro must be constructed manually")


_DISTRO_CONTEXT_REGISTRY = PluginRegistry("context.distro")
provides_distro_context = _DISTRO_CONTEXT_REGISTRY.create_decorator()


@provides_context("distro")
class DistroContextDimension(TmtContextDimension[Distro]):
    _dimension_name = "distro"

    @classmethod
    def _make_value(cls, raw_value: str) -> Distro:
        return Distro.create(raw_value)

    def _op_eq(self, other: str) -> bool:
        try:
            other_value = self._make_value(other)
        except ContextError as err:
            raise CannotDecide from err
        return self.value._op_eq(other_value, minor_mode=False)

    def _op_greater(self, other: str) -> bool:
        try:
            other_value = self._make_value(other)
        except ContextError as err:
            raise CannotDecide from err
        return self.value._op_greater(other_value, minor_mode=False)

    def _op_minor_eq(self, other: str) -> bool:
        try:
            other_value = self._make_value(other)
        except ContextError as err:
            raise CannotDecide from err
        return self.value._op_eq(other_value, minor_mode=True)

    def _op_minor_greater(self, other: str) -> bool:
        try:
            other_value = self._make_value(other)
        except ContextError as err:
            raise CannotDecide from err
        return self.value._op_greater(other_value, minor_mode=True)

    # TODO: Move these into fmf and have a @total_ordering-like decorator
    # Note order of short-circuit matters to avoid going through a branch that,
    # would raise CannotDecide. `_op_eq` must always be tested first for the `or_equal`
    def _op_less(self, other: str) -> bool:
        return not self._op_greater(other) and not self._op_eq(other)

    def _op_less_or_equal(self, other: str) -> bool:
        return self._op_eq(other) or not self._op_greater(other)

    def _op_greater_or_equal(self, other: str) -> bool:
        return self._op_eq(other) or self._op_greater(other)

    def _op_minor_less(self, other: str) -> bool:
        return not self._op_minor_greater(other) and not self._op_minor_eq(other)

    def _op_minor_less_or_equal(self, other: str) -> bool:
        return self._op_minor_eq(other) or not self._op_minor_greater(other)

    def _op_minor_greater_or_equal(self, other: str) -> bool:
        return self._op_minor_eq(other) or self._op_minor_greater(other)
