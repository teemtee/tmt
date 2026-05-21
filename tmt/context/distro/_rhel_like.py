import typing
from abc import ABC
from typing import ClassVar, Literal

from fmf.context import CannotDecide

from tmt._compat.typing import TypeGuard
from tmt.container import container
from tmt.context.distro import Distro

RhelFamily = Literal["fedora", "centos", "rhel"]
RHEL_FAMILIES: list[RhelFamily] = list(typing.get_args(RhelFamily))


def is_rhel_family(val: str) -> TypeGuard[RhelFamily]:
    return val in RHEL_FAMILIES


@container
class RhelLikeDistro(Distro, ABC):
    """
    Base class for comparing RHEL-like distros.
    """

    #: Distro family to help determine how to compare distros
    family: ClassVar[RhelFamily]

    def _assert_compatible_distro(self, other: Distro) -> None:
        if not isinstance(other, RhelLikeDistro):
            raise CannotDecide(
                f"Cannot compare rhel-like distro '{self}' with non-rhel-like '{other}'"
            )
