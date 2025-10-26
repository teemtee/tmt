"""
Artifact provider for repository files.
"""

import re
from collections.abc import Iterator, Sequence
from functools import cached_property
from re import Pattern
from shlex import quote
from typing import Optional
from urllib.parse import unquote, urlparse

import tmt.log
from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
    Repository,
)
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


class RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Provider for making RPM artifacts from a repository discoverable without downloading them.

    The provider identifier should start with 'repository-url:' followed by a URL to a .repo file,
    e.g., "repository-url:https://download.docker.com/linux/centos/docker-ce.repo".

    Artifacts are all available RPM packages listed in the repository
    """

    repository: Repository
    _artifact_list: Optional[Sequence[RpmArtifactInfo]]

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        # Initialize to None to distinguish between "not run" and "run but empty"
        self._artifact_list = None

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        prefix = 'repository-url:'
        if not raw_provider_id.startswith(prefix):
            raise ValueError(f"Invalid repository provider format: '{raw_provider_id}'.")
        value = raw_provider_id[len(prefix) :]
        if not value:
            raise ValueError("Missing repository URL.")
        return value

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        # Check for None to see if fetch_contents() has been called
        if self._artifact_list is None:
            raise tmt.utils.GeneralError("Call fetch_contents first to discover artifacts.")
        # Return the list (which is valid even if it's empty)
        return self._artifact_list

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only sets up the repo, it does not download RPMs."""

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        # Override the default behavior: instead of downloading artifacts,
        # this method makes RPMs from the repository discoverable.

        # 1. Install the repository file on the guest using info from our helper object
        self.repository = Repository.from_url(url=self.id, logger=self.logger)

        # Install the repository using the guest's package manager
        guest.package_manager.install_repository(self.repository)

        # Load the artifacts using list_packages
        package_list = guest.package_manager.list_packages(self.repository)

        # Initialize the list before populating
        self._artifact_list = []

        for pkg in package_list:
            try:
                # Use the new utility function to parse the package string
                raw_artifact = {**parse_rpm_string(pkg_string=pkg), "url": self.id}
                self._artifact_list.append(RpmArtifactInfo(_raw_artifact=raw_artifact))

            except ValueError:
                # Catches both regex failing to match (ValueError)
                # or an explicit ValueError raised by the utility function.
                self.logger.warning(f"Failed to parse malformed package string '{pkg}'. Skipping.")
                continue

            except Exception as error:
                # Catch any other unexpected errors
                self.logger.debug(f"Unexpected error while parsing package '{pkg}': {error}.")
                continue

        self.logger.debug(f"Successfully discovered '{len(self._artifact_list)}' artifacts.")

        return []


# TODO: This is a generic RPM parsing utility and should be moved
# to a more appropriate location, e.g., 'tmt.utils.rpm'.
_PKG_REGEX = re.compile(
    r'^(?P<name>.+)-(?:(?P<epoch>\d+):)?(?P<version>[^-:]+)-(?P<release>[^-:]+)\.(?P<arch>[^.]+)$'
)


def parse_rpm_string(pkg_string: str) -> dict[str, str]:
    """
    Parses a full RPM package string (N-E:V-R.A) into its components.

    :param pkg_string: The package string, e.g., "docker-ce-1:20.10.7-3.el8.x86_64".
    :raises ValueError: if the package string is malformed.
    :return: A dictionary of RPM components.
    """

    # 1. Match the package string against the regex
    match = _PKG_REGEX.match(pkg_string)

    if not match:
        raise ValueError(f"String '{pkg_string}' does not match N-V-R.A format")

    # 2. Extract the named parts
    # Non-optional groups are guaranteed to be strings.
    name = match.group('name')
    version = match.group('version')
    release = match.group('release')
    arch = match.group('arch')

    # Optional epoch group can be None
    epoch = match.group('epoch')
    if epoch is None:
        epoch = '0'

    # Additional validation
    if ':' in name:
        raise ValueError(f"Malformed package string: {pkg_string} colon in package name.")
    if '.' not in version:
        raise ValueError(f"Malformed package string: {pkg_string} no dot in version.")

    # Reconstruct NVR (Name-Version-Release)
    nvr = f"{name}-{version}-{release}"

    return {
        'name': name,
        'epoch': epoch,
        'version': version,
        'release': release,
        'arch': arch,
        'nvr': nvr,
    }
