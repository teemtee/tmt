import re
from typing import Literal

from tmt.context.distro import Distro, Version, provides_distro_context
from tmt.context.distro._rhel_like import RhelLikeDistro


@provides_distro_context("rhel")
class RhelDistro(RhelLikeDistro):
    _DISTRO_PATTERN = re.compile(r"^rhel-?(?P<version>[\d.]*)$")
    family = "rhel"

    @classmethod
    def _create_distro(cls, raw_id: str, match: re.Match[str]) -> Distro:
        return RhelDistro(
            _raw_value=raw_id,
            id="rhel",
            version=Version.from_str(match.group("version")),
        )

    def _eq_unversioned(self, other: Distro) -> bool:
        assert isinstance(other, RhelLikeDistro)  # narrow type
        assert other.version is None  # narrow type

        # rhel is only rhel
        return other.family == "rhel"

    def _compare_version(self, other: Distro, minor_mode: bool = False) -> Literal[-1, 0, 1]:
        assert isinstance(other, RhelLikeDistro)  # narrow type
        assert isinstance(self.version, Version)  # narrow type
        assert other.version  # narrow type

        # Fedora is always newer than rhel
        if other.family == "fedora":
            return -1

        # Comparing against centos
        if other.family == "centos":
            assert isinstance(other.version, Version)  # narrow type
            version_comp = self.version._compare_version(other.version, minor_mode=minor_mode)

            # rhel > centos with lower version
            if version_comp == 1:
                return 1

            #  rhel < centos with same version or higher
            return -1

        # Remaining case is comparing rhel versions, use default logic
        return super()._compare_version(other, minor_mode)
