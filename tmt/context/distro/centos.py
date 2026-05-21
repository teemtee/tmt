import re
from typing import Literal

from tmt.container import container
from tmt.context.distro import Distro, Version, provides_distro_context
from tmt.context.distro._rhel_like import RhelLikeDistro


@provides_distro_context("centos")
@container
class CentosDistro(RhelLikeDistro):
    _DISTRO_PATTERN = re.compile(r"^centos-?(?P<stream>stream)?-?(?P<version>[\d.]*])$")
    family = "centos"
    stream: bool = False

    @classmethod
    def _create_distro(cls, raw_id: str, match: re.Match[str]) -> Distro:
        stream = bool(match.group("stream"))
        return CentosDistro(
            _raw_value=raw_id,
            id="centos",
            version=Version.from_str(match.group("version")),
            stream=stream,
        )

    def _eq_unversioned(self, other: Distro) -> bool:
        assert isinstance(other, RhelLikeDistro)  # narrow type
        assert other.version is None  # narrow type

        # centos is not Fedora
        if other.family == "fedora":
            return False

        # centos is rhel-like
        if other.family == "rhel":
            return True

        assert isinstance(other, CentosDistro)  # narrow type
        if other.stream:
            # Centos-stream-X is centos-stream
            # Centos-X is not centos-stream
            return self.stream
        # All centos are centos
        return True

    def _compare_version(self, other: Distro, minor_mode: bool = False) -> Literal[-1, 0, 1]:
        assert isinstance(other, RhelLikeDistro)  # narrow type
        assert self.version  # narrow type
        assert other.version  # narrow type

        # Fedora is always newer than rhel
        if other.family == "fedora":
            return -1

        # Comparing against rhel
        if other.family == "rhel":
            assert isinstance(other.version, Version)  # narrow type
            version_comp = self.version._compare_version(other.version, minor_mode=minor_mode)

            # centos < rhel with higher version
            if version_comp == -1:
                return -1
            # centos > rhel with same version or lower
            return 1

        # Remaining case is comparing centos versions, use default logic
        assert isinstance(other, CentosDistro)  # narrow type
        version_comp = super()._compare_version(other, minor_mode=minor_mode)
        # Same types return comparison as it should be
        if self.stream == other.stream:
            return version_comp
        # Comparing centos stream against non-stream
        if self.stream:
            # Stream version is newer than non-stream with same version
            if version_comp == 0:
                return 1
            # Otherwise normal comparison holds
            return version_comp
        # Comparing centos non-stream against stream
        assert other.stream
        # Non-stream version is older than stream with same version
        if version_comp == 0:
            return -1
        # Otherwise normal comparison holds
        return version_comp
