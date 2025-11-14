"""
Artifact provider for discovering RPMs from repository files.
"""

import re
from collections.abc import Sequence
from pyexpat.errors import messages
from re import Pattern
from typing import Optional
from urllib.parse import unquote, urlparse

import tmt.log
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    Repository,
    provides_artifact_provider,
)
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path


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

    @property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        """
        List all RPMs discovered from the repositories.

        .. note::

            The :py:meth:`fetch_contents` method must be called first to populate
            the artifact list from the guest.
        """
        # Check for None to see if fetch_contents() has been called
        if self._artifact_list is None:
            raise tmt.utils.GeneralError("Call fetch_contents first to discover artifacts.")
        # Return the list (which is valid even if it's empty)
        return self._artifact_list

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only discovers repos; it does not download individual RPMs."""
        raise AssertionError(
            "RepositoryFileProvider does not support downloading individual RPMs."
        )

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        # Override the default behavior: instead of downloading artifacts,
        # this method makes RPMs from the repository discoverable.
        # TODO: Add support for src RPM's

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

        self.logger.debug(f"Successfully discovered '{len(self._artifact_list)}' artifacts.")

        return []


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
    Create and install a local RPM repository from a directory on the guest.

    This function orchestrates the complete process of creating a local RPM repository
    from a directory containing RPM packages and installing it on the guest system.
    The process involves:

    1. Creating repository metadata in the specified directory using the guest's package manager
    2. Generating a .repo configuration file with the repository settings
    3. Installing the repository configuration file on the guest system


    :param artifact_dir: Path to the directory on the guest containing RPM files.
                         This directory must exist on the guest system.
    :param guest: Guest instance where the repository will be created and installed.
    :param logger: Logger instance for outputting debug and error messages.
    :param repo_name: Name for the repository. If not provided, the directory name
                      will be used. This name appears in the .repo file and package
                      manager output.
    :param priority: Repository priority (default: 1). Lower values have higher
                     priority when multiple repositories provide the same package.
    :return: Repository object representing the newly created and installed repository.
    :raises GeneralError: If the artifact directory does not exist on the guest,
                         if repository metadata creation fails, or if repository
                         installation fails.

    .. note::

        The repository is created with ``gpgcheck=0`` (GPG signature checking disabled)
        to support unsigned local packages.

    Example::

        # Create repository from downloaded artifacts
        repository = create_repository(
            artifact_dir=Path('/tmp/my-rpms'),
            guest=my_guest,
            logger=my_logger,
            repo_name='my-local-repo',
            priority=1
        )

    """

    # Validation
    if repo_name is None:
        repo_name = artifact_dir.name
        if not repo_name:
            raise GeneralError(
                f"Could not derive repository name from directory '{artifact_dir}'."
            )

    logger.debug(f"Creating repository '{repo_name}' from '{artifact_dir}'.")
    try:
        guest.execute(
            tmt.utils.Command("test", "-d", str(artifact_dir)),
            silent=True,
        )
    except tmt.utils.RunError as error:
        raise GeneralError(
            f"Artifact directory '{artifact_dir}' does not exist on guest."
        ) from error

    # Create Repository Metadata
    logger.debug(f"Asking package manager to create metadata in '{artifact_dir}'.")
    try:
        # This now calls the correct method (e.g., in DnfPackageManager)
        guest.package_manager.create_repository_metadata_from_dir(artifact_dir)
    except (NotImplementedError, GeneralError) as error:
        raise GeneralError(f"Failed to create repository metadata in '{artifact_dir}'") from error

    # Generate .repo File Content
    repo_content = [
        f"[{tmt.utils.sanitize_name(repo_name)}]",
        f"name={repo_name}",
        f"baseurl=file://{artifact_dir}",
        "enabled=1",
        "gpgcheck=0",
        f"priority={priority}",
    ]
    repo_string = "\n".join(repo_content)
    logger.debug(f"Generated .repo file content:\n{repo_string}")

    # Create and Install Repository Object
    created_repository = Repository.from_content(
        content=repo_string, name=repo_name, logger=logger
    )

    logger.debug(f"Installing repository '{created_repository.name}' on the guest.")

    guest.package_manager.install_repository(created_repository)

    return created_repository
