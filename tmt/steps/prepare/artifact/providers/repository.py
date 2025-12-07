"""
Artifact provider for discovering RPMs from repository files.
"""

import configparser
import re
from collections.abc import Sequence
from functools import cached_property
from io import StringIO
from re import Pattern
from shlex import quote
from typing import Optional
from urllib.parse import urlparse

import tmt.log
from tmt.steps import DefaultNameGenerator
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    Repository,
    provides_artifact_provider,
)
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, PrepareError, RunError

# Counter for generating unique repository names in the format ``tmt-repo-default-{n}``.
_REPO_NAME_GENERATOR = DefaultNameGenerator(known_names=[])


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('repository-url')  # type: ignore[arg-type]
class RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Provider for making RPM artifacts from a repository discoverable without downloading them.

    The provider identifier should start with 'repository-url:' followed by a URL to a .repo file,
    e.g., "repository-url:https://download.docker.com/linux/centos/docker-ce.repo".

    The provider downloads the .repo file to the guest's ``/etc/yum.repos.d/`` directory,
    and lists RPMs available in the defined repositories without downloading them, acting as a
    discovery-only provider. Artifacts are all available RPM packages listed in the repository.

    :param raw_provider_id: The full provider identifier, starting with 'repository-url:'.
    :param logger: Logger instance for outputting messages.
    :raises GeneralError: If the .repo file URL is invalid.
    """

    repository: Repository

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)

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
        """
        List all RPMs discovered from the repositories.

        For repository-url providers, artifacts are discovered dynamically when
        fetch_contents() is called during the prepare step. This property returns
        an empty list as a placeholder, since the actual packages are made available
        through the repository system rather than being downloaded as individual files.

        The actual artifact discovery happens in _discover_packages() which is called
        from fetch_contents() during the workflow execution.

        :returns: empty list (artifacts are discovered at runtime via repository).
        """
        # Repository providers don't enumerate artifacts upfront since they come
        # from remote repositories. Return empty list to satisfy the interface.
        return []

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only discovers repos; it does not download individual RPMs."""
        raise AssertionError(
            "RepositoryFileProvider does not support downloading individual RPMs."
        )

    def _discover_packages(
        self,
        guest: Guest,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> int:
        """
        Discover packages available in the repository for logging purposes.

        This method installs the repository to query available packages and returns
        the count for informational logging. The repository will remain installed.

        :param guest: the guest on which to discover packages.
        :param exclude_patterns: if set, artifacts whose names match any
            of the given regular expressions would be excluded.
        :returns: number of packages discovered.
        """
        # TODO: Add support for src RPM's

        # Ensure repository is initialized
        if not hasattr(self, 'repository') or self.repository is None:
            raise GeneralError("Repository not initialized. Call contribute_to_shared_repo first.")

        # Install the repository using the guest's package manager to query it
        guest.package_manager.install_repository(self.repository)

        # Load the artifacts using list_packages
        package_list = guest.package_manager.list_packages(self.repository)

        # Count packages for logging
        package_count = 0

        for pkg in package_list:
            try:
                # Use the new utility function to parse the package string
                raw_artifact = {**parse_rpm_string(pkg_string=pkg), "url": self.id}
                artifact = RpmArtifactInfo(_raw_artifact=raw_artifact)

                # Apply exclude patterns
                if exclude_patterns and any(
                    pattern.search(artifact.id) for pattern in exclude_patterns
                ):
                    self.logger.debug(
                        f"Excluding artifact '{artifact.id}' based on exclude patterns."
                    )
                    continue

                package_count += 1
            except ValueError as error:
                # Catches both regex failing to match (ValueError)
                # or an explicit ValueError raised by the utility function.
                tmt.utils.show_exception_as_warning(
                    exception=error,
                    message=f"Failed to parse malformed package string '{pkg}'. Skipping.",
                    logger=self.logger,
                )
                continue

            except Exception as error:
                # Catch any other unexpected errors
                tmt.utils.show_exception_as_warning(
                    exception=error,
                    message=f"Unexpected error while parsing package '{pkg}': {error}.",
                    logger=self.logger,
                )
                continue

        self.logger.debug(
            f"Successfully discovered '{package_count}' packages "
            f"in repository '{self.repository.name}'."
        )
        return package_count

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        """
        Discover packages from the repository without downloading them.

        This method overrides the default behavior - instead of downloading artifacts,
        it discovers what packages are available in the repository.

        :param guest: the guest on which to discover packages.
        :param download_path: unused for this provider.
        :param exclude_patterns: if set, artifacts whose names match any
            of the given regular expressions would be excluded.
        :returns: empty list (no files are downloaded).
        """
        self._discover_packages(guest, exclude_patterns)
        return []

    def get_repositories(self) -> list[Repository]:
        """
        Return the repository object managed by this provider.

        :returns: list containing the repository to be installed.
        """
        if not hasattr(self, 'repository') or self.repository is None:
            raise tmt.utils.GeneralError(
                "Repository not initialized. Call contribute_to_shared_repo first."
            )
        return [self.repository]

    def _add_priority_to_repo_content(self, content: str, priority: int = 1) -> str:
        """
        Add or update priority setting in repository configuration.

        This ensures the repository takes precedence over system repositories
        when installing packages. Lower priority values have higher precedence.

        :param content: The original .repo file content.
        :param priority: The priority value to set (default: 1).
        :returns: Modified content with priority setting added to all sections.
        """
        config = configparser.ConfigParser()
        try:
            config.read_string(content)
        except configparser.Error as error:
            raise GeneralError(f"Failed to parse repository content: {error}") from error

        # Add priority to all repository sections
        for section in config.sections():
            config.set(section, 'priority', str(priority))

        # Write the modified configuration to a string
        output = StringIO()
        config.write(output)
        return output.getvalue()

    def contribute_to_shared_repo(
        self,
        guest: Guest,
        download_path: Path,
        shared_repo_dir: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> None:
        """
        Prepare the repository for installation.

        This provider fetches repository files from URLs and prepares them for
        installation. It does not contribute artifacts to the shared repository
        since it works with remote repositories. The repository will be installed
        later via get_repositories().

        :param guest: the guest on which the repository will be installed.
        :param download_path: used for storing repository files from file:// URLs.
        :param shared_repo_dir: unused for this provider.
        :param exclude_patterns: unused for this provider.
        """
        # Fetch the repository from URL (only if not already initialized)
        if not hasattr(self, 'repository') or self.repository is None:
            # Check if the URL is a file:// URL
            parsed_url = urlparse(self.id)
            if parsed_url.scheme == 'file':
                # For file:// URLs, we need to:
                # 1. Read the file from the host filesystem
                # 2. Copy it to the guest via guest.push
                # 3. Create a Repository from the guest's copy

                host_file_path = Path(parsed_url.path)

                # Read the content from the host
                try:
                    content = host_file_path.read_text()
                except OSError as error:
                    raise GeneralError(
                        f"Failed to read repository file '{host_file_path}' from host."
                    ) from error

                # Derive repository name from the file path
                repo_name = host_file_path.name.removesuffix('.repo')
                if not repo_name:
                    raise GeneralError(
                        f"Could not derive repository name from path '{host_file_path}'."
                    )

                # Add priority=1 to the repository configuration to ensure it takes
                # precedence over system repositories. This is important when the
                # repository-url provider is used to test specific packages.
                content = self._add_priority_to_repo_content(content, priority=1)

                # Create Repository object with the content
                self.repository = Repository.from_content(
                    content=content, name=repo_name, logger=self.logger
                )
            else:
                # Use from_url for http:// and https:// URLs
                self.repository = Repository.from_url(url=self.id, logger=self.logger)

                # Add priority to ensure the repository takes precedence
                self.repository = Repository.from_content(
                    content=self._add_priority_to_repo_content(
                        self.repository.content, priority=1
                    ),
                    name=self.repository.name,
                    logger=self.logger,
                )
            self.logger.debug(f"Prepared repository '{self.repository.name}' for installation.")


# FIXME: Make this function more robust. The current regex-based parsing
# is a "happy path" implementation and will fail on complex or
# unusually-named packages. This is acceptable for now but should
# be hardened later
# Regex to parse N-E:V-R.A format.
# Groups: 1:Name, 3:Epoch (optional), 4:Version, 5:Release, 6:Arch
_PKG_REGEX = re.compile(
    r"""
    ^                                   # must match the whole string
    (?P<name>[^:]+)                     # Name (one or more characters except colon)
    -                                   # literal hyphen
    ((?P<epoch>\d+):)?                  # optional group: epoch (one or more digits)
                                        # followed by colon
    (?P<version>[^-:]*\d[^-:]*)         # Version (zero or more non-hyphen/colon,
                                        # at least one digit, zero or more non-hyphen/colon)
    -                                   # literal hyphen
    (?P<release>[^-]+)                  # Release (one or more non-hyphen characters)
    \.                                  # literal dot
    (?P<arch>[^.]+)                     # Arch (one or more non-dot characters)
    """,
    re.VERBOSE,
)


def parse_rpm_string(pkg_string: str) -> dict[str, str]:
    """
    Parses a full RPM package string (N-E:V-R.A) into its components.

    :param pkg_string: The package string, e.g., "docker-ce-1:20.10.7-3.el8.x86_64".
    :raises ValueError: if the package string is malformed.
    :return: A dictionary of RPM components.
    """

    # 1. Match the package string against the regex
    match = _PKG_REGEX.fullmatch(pkg_string)

    if not match:
        raise ValueError(f"String '{pkg_string}' does not match N-E:V-R.A format")

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


def create_repository(
    artifact_dir: Path,
    guest: Guest,
    logger: tmt.log.Logger,
    repo_name: Optional[str] = None,
    priority: int = 1,
) -> Repository:
    """
    Create a local RPM repository from a directory on the guest.

    Creates the directory if needed, creates repository metadata, and prepares
    a Repository object. Does not install the repository on the guest system.
    Use install_repository() to make it visible to the package manager.

    :param artifact_dir: Path to the directory on the guest containing RPM files.
    :param guest: Guest instance where the repository metadata will be created.
    :param logger: Logger instance for outputting debug and error messages.
    :param repo_name: Name for the repository. If not provided, generates a unique
        name using the format ``tmt-repo-default-{n}``.
    :param priority: Repository priority (default: 1). Lower values have higher priority.
    :returns: Repository object representing the newly created repository.
    :raises PrepareError: If the package manager does not support creating repositories
        or if metadata creation fails.
    """

    repo_name = repo_name or f"tmt-repo-{_REPO_NAME_GENERATOR.get()}"

    # Create the repository directory on the guest
    guest.execute(
        tmt.utils.ShellScript(f"mkdir -p {quote(str(artifact_dir))}"),
        silent=True,
    )

    # Create Repository Metadata
    logger.debug(f"Creating metadata for '{artifact_dir}'.")
    try:
        guest.package_manager.create_repository(artifact_dir)
    except RunError as error:
        raise PrepareError(f"Failed to create repository metadata in '{artifact_dir}'") from error

    # Generate .repo File Content
    repo_string = f"""[{tmt.utils.sanitize_name(repo_name)}]
name={repo_name}
baseurl=file://{artifact_dir}
enabled=1
gpgcheck=0
priority={priority}"""

    logger.debug(f"Generated .repo file content:\n{repo_string}")

    # Create Repository Object
    created_repository = Repository.from_content(
        content=repo_string, name=repo_name, logger=logger
    )

    logger.debug(f"Created repository '{created_repository.name}' (not yet installed).")

    return created_repository
