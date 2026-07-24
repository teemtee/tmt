"""
RPM-specific version type shared across package managers and artifact providers.
"""

import re
from typing import Any, Optional

from tmt._compat.typing import Self
from tmt.container import container
from tmt.package_managers import Version

NEVRA_PATTERN = re.compile(
    r'^(?P<name>.+)-(?:(?P<epoch>\d+):)?(?P<version>.+)-(?P<release>.+)\.(?P<arch>.+)$'
)


@container(frozen=True)
class RpmVersion(Version):
    """
    Represents an RPM package version.
    """

    #: The repository section ID this package was listed from, if known.
    repo_id: Optional[str] = None

    @classmethod
    def from_rpm_meta(cls, rpm_meta: dict[str, Any]) -> Self:
        """
        Version constructed from RPM metadata dictionary.

        Example usage:

        .. code-block:: python

            version_info = RpmVersion.from_rpm_meta({
                "name": "curl",
                "version": "8.11.1",
                "release": "7.fc42",
                "arch": "x86_64"
            })
        """
        return cls(
            name=rpm_meta["name"],
            version=rpm_meta["version"],
            release=rpm_meta["release"],
            arch=rpm_meta["arch"],
            epoch=rpm_meta.get("epoch", 0),
        )

    @classmethod
    def from_filename(cls, filename: str) -> Self:
        """
        Version constructed from RPM filename.

        Example usage:

        .. code-block:: python

            version_info = RpmVersion.from_filename("curl-8.11.1-7.fc42.x86_64.rpm")
        """
        base = filename.removesuffix(".rpm")
        nvr_part, *arch_parts = base.rsplit(".", 1)
        arch = arch_parts[0] if arch_parts else "noarch"
        parts = nvr_part.rsplit("-", 2)
        if len(parts) != 3:
            raise ValueError(
                f"Invalid RPM filename format: '{filename}'. "
                f"Expected name-version-release.arch.rpm"
            )
        name, version, release = parts

        return cls(name=name, version=version, release=release, arch=arch, epoch=0)

    @classmethod
    def from_nevra(cls, nevra: str, repo_id: Optional[str] = None) -> Self:
        """
        Version constructed from a NEVRA string as returned by ``dnf repoquery``.

        Example usage:

        .. code-block:: python

            version_info = RpmVersion.from_nevra("curl-0:8.11.1-7.fc42.x86_64")
            version_info = RpmVersion.from_nevra("curl-8.11.1-7.fc42.x86_64")
        """
        match = NEVRA_PATTERN.match(nevra)
        if not match:
            raise ValueError(f"Cannot parse NEVRA '{nevra}'.")

        return cls(
            name=match.group('name'),
            epoch=int(match.group('epoch') or 0),
            version=match.group('version'),
            release=match.group('release'),
            arch=match.group('arch'),
            repo_id=repo_id,
        )
