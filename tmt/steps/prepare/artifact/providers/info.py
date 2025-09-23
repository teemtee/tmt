"""
Artifact Info classes.

Defines metadata representations for different artifact types.
"""

from abc import ABC, abstractmethod
from typing import Any

from tmt.container import container


@container
class ArtifactInfo(ABC):
    """
    Information about a single artifact.

    Attributes:
        id (str): A unique identifier for the artifact.
                  * RPMs → 'tmt-1.58.0.dev21+gb229884df-main.fc41.noarch'
                  * Containers → image digest or tag
    """

    _raw_artifact: dict[str, Any]

    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def location(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.id


@container
class RpmArtifactInfo(ArtifactInfo):
    """
    Represents a single RPM file from Koji.
    """

    PKG_URL = "https://kojipkgs.fedoraproject.org/packages/"  # For actual package downloads

    @property
    def id(self) -> str:
        """A koji rpm identifier"""
        return f"{self._raw_artifact['nvr']}.{self._raw_artifact['arch']}.rpm"

    @property
    def location(self) -> str:
        """Get the download URL for the given RPM metadata."""
        return (
            f"{self.PKG_URL}{self._raw_artifact['name']}/"
            f"{self._raw_artifact['version']}/"
            f"{self._raw_artifact['release']}/"
            f"{self._raw_artifact['arch']}/"
            f"{self.id}"
        )
