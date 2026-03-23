"""
RPM-related types shared across package managers and artifact providers.
"""

import configparser
from typing import Any, Optional
from urllib.parse import urlparse

import tmt.log
import tmt.utils
from tmt._compat.typing import Self
from tmt.container import container, simple_field
from tmt.utils import GeneralError, Path


@container(frozen=True)
class Version:
    """
    Version information for artifacts.
    """

    name: str
    version: str
    release: str
    arch: str
    epoch: int = 0

    @property
    def nvra(self) -> str:
        return f"{self.name}-{self.version}-{self.release}.{self.arch}"

    @property
    def nevra(self) -> str:
        return f"{self.name}-{self.epoch}:{self.version}-{self.release}.{self.arch}"

    def __str__(self) -> str:
        return self.nvra


@container(frozen=True)
class RpmVersion(Version):
    """
    Represents an RPM package version.
    """

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


@container
class Repository:
    """
    Thin wrapper/holder for .repo file content
    """

    #: Content of the repository
    content: str
    #: Uniquely identifiable name
    name: str
    #: repository_ids present in the .repo file
    repo_ids: list[str] = simple_field(default_factory=list[str])

    def __post_init__(self) -> None:
        """
        Extract repository IDs from the .repo file content after initialization.

        :raises GeneralError: If the content is malformed or no repository
            sections are found.
        """
        config = configparser.ConfigParser()
        try:
            config.read_string(self.content)
            sections = config.sections()
            if not sections:
                raise GeneralError(
                    f"No repository sections found in the content for '{self.name}'."
                )
            # Store the parsed sections in our private attribute
            self.repo_ids = sections
        except configparser.MissingSectionHeaderError as error:
            raise GeneralError(
                f"No repository sections found in the content for '{self.name}'."
            ) from error
        except configparser.Error as error:
            raise GeneralError(
                f"Failed to parse the content of repository '{self.name}'. "
                "The .repo file may be malformed."
            ) from error

    @classmethod
    def from_url(
        cls, url: str, logger: tmt.log.Logger, name: Optional[str] = None
    ) -> "Repository":
        """
        Create a Repository instance by fetching content from a URL.

        :param url: The URL to fetch the repository content from.
        :param logger: Logger to use for the operation.
        :param name: Optional name for the repository. If not provided,
            derived from the URL.
        :returns: A Repository instance.
        :raises GeneralError: If fetching or parsing fails.
        """
        try:
            with tmt.utils.retry_session(logger=logger) as session:
                response = session.get(url)
                response.raise_for_status()
                content = response.text
        except Exception as error:
            raise GeneralError(f"Failed to fetch repository content from '{url}'.") from error

        if name is None:
            parsed_url = urlparse(url)
            parsed_path = parsed_url.path.rstrip('/').split('/')[-1]
            name = parsed_path.removesuffix('.repo')
            if not name:
                raise GeneralError(f"Could not derive repository name from URL '{url}'.")

        return cls(name=name, content=content)

    @classmethod
    def from_file_path(
        cls, file_path: Path, logger: tmt.log.Logger, name: Optional[str] = None
    ) -> "Repository":
        """
        Create a Repository instance by reading content from a local file path.

        :param file_path: The local path to the repository file.
        :param logger: Logger to use for the operation.
        :param name: Optional name for the repository. If not provided,
            derived from the file path.
        :returns: A Repository instance.
        :raises GeneralError: If reading the file fails.
        """
        try:
            content = file_path.read_text()
        except OSError as error:
            raise GeneralError(f"Failed to read repository file '{file_path}'.") from error

        if name is None:
            name = file_path.stem
            if not name:
                raise GeneralError(
                    f"Could not derive repository name from file path '{file_path}'."
                )

        return cls(name=name, content=content)

    @classmethod
    def from_content(cls, content: str, name: str, logger: tmt.log.Logger) -> "Repository":
        """
        Create a Repository instance directly from provided content string.

        :param content: The string content of the repository.
        :param name: The name for the repository (required when using content).
        :param logger: Logger to use for the operation.
        :returns: A Repository instance.
        :raises GeneralError: If the name is empty.
        """
        if not name:
            raise GeneralError("Repository name cannot be empty.")
        return cls(name=name, content=content)

    @property
    def filename(self) -> str:
        """The name of the .repo file (e.g., 'my-repo.repo')."""
        return f"{tmt.utils.sanitize_name(self.name)}.repo"
