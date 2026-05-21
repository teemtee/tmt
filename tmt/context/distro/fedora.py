import re
import typing
from typing import Literal

from tmt._compat.typing import TypeGuard
from tmt.context import ContextError
from tmt.context.distro import Distro, Version, provides_distro_context
from tmt.context.distro._rhel_like import RhelLikeDistro

# TODO: Can support latest alias using fedora-distro-aliases
FedoraAlias = Literal["rawhide", "eln"]
FEDORA_ALIASES: list[FedoraAlias] = list(typing.get_args(FedoraAlias))


def is_fedora_alias(val: str) -> TypeGuard[FedoraAlias]:
    return val in FEDORA_ALIASES


@provides_distro_context("fedora")
class FedoraDistro(RhelLikeDistro):
    _DISTRO_PATTERN = re.compile(r"^fedora-?(?P<version>.*)$")
    family = "fedora"

    @classmethod
    def _create_distro(cls, raw_id: str, match: re.Match[str]) -> Distro:
        version_or_alias = match.group("version")
        if not version_or_alias:
            return FedoraDistro(
                _raw_value=raw_id,
                id="fedora",
                version=None,
            )
        if is_fedora_alias(version_or_alias):
            return FedoraDistro(
                _raw_value=raw_id,
                id="fedora",
                version=version_or_alias,
            )
        version = Version.from_str(version_or_alias)
        if not version:
            raise ContextError(f"Could not determine fedora version of context '{raw_id}'")
        if len(version.parts) > 1:
            raise ContextError(f"Fedora does not have minor versions: '{raw_id}'")
        return FedoraDistro(
            _raw_value=raw_id,
            id="fedora",
            version=version,
        )

    def _eq_unversioned(self, other: Distro) -> bool:
        assert isinstance(other, RhelLikeDistro)  # narrow type
        assert other.version is None  # narrow type

        # eln is the same as fedora and other rhel-like
        if self.version == "eln":
            return True
        # everything else is *only* fedora
        return other.family == "fedora"

    def _compare_version(self, other: Distro, minor_mode: bool = False) -> Literal[-1, 0, 1]:
        assert isinstance(other, RhelLikeDistro)  # narrow type
        assert self.version  # narrow type
        assert other.version  # narrow type

        # Fedora and eln are always newer than rhel or centos
        if other.family != "fedora":
            return 1

        # Comparing against rawhide
        if other.version == "rawhide":
            if self.version == "rawhide":
                return 0
            # rawhide > any version
            return -1

        # Comparing against eln target
        if other.version == "eln":
            # Rawhide > eln
            if self.version == "rawhide":
                return 1
            # eln == eln (of course)
            if self.version == "eln":
                return 0
            # Any versioned Fedora < eln
            assert isinstance(other.version, Version)
            return -1

        assert isinstance(other.version, Version)
        if not isinstance(self.version, Version):
            # rawhide and eln > any versioned Fedora
            return 1

        # Remaining case is comparing fedora versions, use default logic
        return super()._compare_version(other, minor_mode=minor_mode)
