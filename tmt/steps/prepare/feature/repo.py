from typing import Literal, Optional

import tmt
import tmt.log
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.container import container, field
from tmt.steps.provision import Guest
from tmt.utils import Command, Environment, Path, RunError


@container
class PrepareRepoData(tmt.steps.prepare.PrepareStepData):
    repos: list[str] = field(
        default_factory=list,
        option=('-r', '--repo'),
        metavar='URL',
        multiple=True,
        help='URLs of Yum .repo files to download and configure.',
        normalize=tmt.utils.normalize_string_list,
    )
    destination: Path = field(
        default=Path('/etc/yum.repos.d'),
        option=('-d', '--destination'),
        metavar='PATH',
        help='Path to store .repo files (default: /etc/yum.repos.d).',
        normalize=lambda key_address, value, logger: Path(value),
    )
    missing: Literal['skip', 'fail'] = field(
        default='fail',
        option=('-m', '--missing'),
        metavar='ACTION',
        choices=['fail', 'skip'],
        help='Action on missing repositories, fail (default) or skip.',
    )


@tmt.steps.provides_method('repo')
class PrepareRepo(tmt.steps.prepare.PreparePlugin[PrepareRepoData]):
    """
    Download and configure Yum repositories on the guest.

    Example config::

        prepare:
            how: repo
            repos:
                - https://example.com/repos/myrepo.repo
            destination: /etc/yum.repos.d
            missing: skip
    """

    _data_class = PrepareRepoData

    def go(
        self, *, guest: Guest, environment: Optional[Environment] = None, logger: tmt.log.Logger
    ) -> tmt.steps.PluginOutcome:
        """
        Download Yum .repo files and configure them on the guest.
        """
        outcome = super().go(guest=guest, environment=environment, logger=logger)

        if self.is_dry_run:
            return outcome

        # Validate package manager
        if guest.facts.package_manager not in ('yum', 'dnf', 'dnf5'):
            raise tmt.utils.PrepareError(
                f"Package manager '{guest.facts.package_manager}' is "
                f"not supported by 'prepare/repo'."
            )

        # Check for curl availability
        try:
            guest.execute(Command('command', '-v', 'curl'), silent=True)
        except RunError:
            raise tmt.utils.PrepareError("Required command 'curl' not found on guest.")

        # Ensure destination directory exists
        destination = self.data.destination
        try:
            guest.execute(Command('mkdir', '-p', str(destination)), silent=True)
        except RunError as error:
            raise tmt.utils.PrepareError(
                f"Failed to create destination directory '{destination}': {error}"
            )

        # Download and configure each repo
        for repo_url in self.data.repos:
            self.info('repo', repo_url, 'green')
            try:
                self._setup_repository(guest, repo_url, destination, logger)
            except RunError as error:
                if self.data.missing == 'skip':
                    self.warn(f"Failed to configure repository '{repo_url}': {error}")
                    continue
                raise tmt.utils.PrepareError(
                    f"Failed to configure repository '{repo_url}': {error}"
                )

        return outcome

    def _setup_repository(
        self, guest: Guest, repo_url: str, destination: Path, logger: tmt.log.Logger
    ) -> None:
        """
        Download and configure a single Yum .repo file.
        """
        logger.debug(f"Configuring Yum repository from '{repo_url}' to '{destination}'")

        # Validate URL ends with .repo
        if not repo_url.endswith('.repo'):
            raise tmt.utils.PrepareError(f"Repository URL '{repo_url}' must end with '.repo'")

        repo_name = Path(repo_url).name
        repo_path = destination / repo_name

        # Download .repo file using curl
        try:
            guest.execute(Command('curl', '-LOf', repo_url), cwd=destination, silent=True)
        except RunError as error:
            if 'not found' in str(error).lower():
                raise tmt.utils.PrepareError(f"Yum repository '{repo_url}' not found")
            raise

        # Verify the file exists and has valid content
        try:
            guest.execute(Command('test', '-f', str(repo_path)), silent=True)
            guest.execute(Command('grep', '-q', r'^\[.*\]', str(repo_path)), silent=True)
        except RunError as error:
            raise tmt.utils.PrepareError(f"Invalid or missing .repo file '{repo_path}': {error}")
