import re
from typing import TYPE_CHECKING, Any, ClassVar, Optional, cast

from tmt._compat.pathlib import Path
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackageManager,
    PackageManagerEngine,
    escape_installables,
    provides_package_manager,
)

if TYPE_CHECKING:
    from tmt._compat.typing import TypeAlias

    # TODO: Move Repository abstraction to tmt.package_manager subpackage
    # This class will be added in a future PR.
    # For now, just type it as Any to satisfy pyright.
    Repository: TypeAlias = Any
else:
    Repository: Any = None  # type: ignore[assignment]

from tmt.utils import Command, CommandOutput, GeneralError, PrepareError, RunError, ShellScript

COPR_URL = 'https://copr.fedorainfracloud.org/coprs'
COPR_REPO_PATTERN = re.compile(r'^(@)?([^/]+)/([^/]+)$')


def parse_copr_repo(copr_repo: str) -> tuple[bool, str, str]:
    """
    Parse a COPR repository identifier into its components.
    """
    matched = COPR_REPO_PATTERN.match(copr_repo)
    if not matched:
        raise PrepareError(f"Invalid copr repository '{copr_repo}'.")
    is_group, name, project = matched.groups()
    return bool(is_group), name, project


def build_copr_repo_url(copr_repo: str, chroot: str) -> str:
    """
    Construct the URL for a COPR ``.repo`` file.
    """
    is_group, name, project = parse_copr_repo(copr_repo)
    group = 'group_' if is_group else ''
    parts = [COPR_URL] + (['g'] if is_group else [])
    parts += [name, project, 'repo', chroot]
    parts += [f"{group}{name}-{project}-{chroot}.repo"]
    return '/'.join(parts)


class DnfEngine(PackageManagerEngine):
    _base_command = Command('dnf')
    _base_debuginfo_command = Command('debuginfo-install')

    skip_missing_packages_option = '--skip-broken'
    skip_missing_debuginfo_option = skip_missing_packages_option

    def prepare_command(self) -> tuple[Command, Command]:
        options = Command('-y')

        command = self._base_command

        if self.guest.facts.sudo_prefix:
            command = Command(self.guest.facts.sudo_prefix) + self._base_command

        return (command, options)

    def _extra_dnf_options(self, options: Options, command: Optional[Command] = None) -> Command:
        """
        Collect additional options for ``yum``/``dnf`` based on given options
        """

        command = command or self._base_command

        extra_options = Command()

        for package in options.excluded_packages:
            extra_options += Command('--exclude', package)

        if options.skip_missing:
            if str(command) == str(self._base_command):
                extra_options += Command(self.skip_missing_packages_option)

            elif str(command) == str(self._base_debuginfo_command):
                extra_options += Command(self.skip_missing_debuginfo_option)

            else:
                raise GeneralError(f"Unhandled package manager command '{command}'.")

        return extra_options

    def _construct_presence_script(
        self, *installables: Installable, what_provides: bool = True
    ) -> ShellScript:
        if what_provides:
            return ShellScript(
                f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}'
            )

        return ShellScript(f'rpm -q {" ".join(escape_installables(*installables))}')

    def check_presence(self, *installables: Installable) -> ShellScript:
        return self._construct_presence_script(*installables)

    def _construct_install_script(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options)

        script = ShellScript(
            f'{self.command.to_script()} install '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'
        )

        if options.check_first:
            script = self._construct_presence_script(*installables) | script

        return script

    def _construct_reinstall_script(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options)

        script = ShellScript(
            f'{self.command.to_script()} reinstall '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'
        )

        if options.check_first:
            script = self._construct_presence_script(*installables) & script

        return script

    def _construct_install_debuginfo_script(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options, command=self._base_debuginfo_command)

        return ShellScript(
            f'{self._base_debuginfo_command.to_script()} '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'
        )

    def refresh_metadata(self) -> ShellScript:
        return ShellScript(
            f'{self.command.to_script()} makecache {self.options.to_script()} --refresh'
        )

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._construct_install_script(*installables, options=options)

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._construct_reinstall_script(*installables, options=options)

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()

        # Make sure debuginfo-install is present on the target system
        if self._base_debuginfo_command == Command('debuginfo-install'):
            script = self.install(FileSystemPath('/usr/bin/debuginfo-install'))

            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_install_debuginfo_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables, options=options
                ),
            )

        else:
            script = cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_install_debuginfo_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables, options=options
                ),
            )

        # Extra ignore/check for yum to workaround BZ#1920176
        if not options.skip_missing:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *tuple(Package(f'{installable}-debuginfo') for installable in installables),
                    what_provides=False,
                ),
            )

        return script

    def install_repository(self, repository: Repository) -> ShellScript:
        repo_path = f"/etc/yum.repos.d/{repository.filename}"
        return ShellScript(
            f"{self.guest.facts.sudo_prefix} tee {repo_path} <<'EOF'\n{repository.content}\nEOF"
        )

    def list_packages(self, repository: Repository) -> ShellScript:
        repo_ids = " ".join(f"--enablerepo={repo_id}" for repo_id in repository.repo_ids)
        return ShellScript(
            f"""
            {self.command.to_script()} repoquery --disablerepo='*' {repo_ids}
            """
        )

    def create_repository(self, directory: Path) -> ShellScript:
        """
        Create repository metadata for package files in the given directory.

        :param directory: The path to the directory containing RPM packages.
        :returns: A shell script to create repository metadata.
        """
        return ShellScript(f"createrepo {directory}")


@provides_package_manager('dnf')
class Dnf(PackageManager[DnfEngine]):
    NAME = 'dnf'

    _engine_class = DnfEngine

    #: Package name of the COPR plugin for this package manager.
    copr_plugin: ClassVar[str] = 'dnf-plugins-core'

    # Compiled regex patterns for DNF/YUM error messages
    _FAILED_PACKAGE_INSTALLATION_PATTERNS = [
        re.compile(r'Unable to find a match:\s+([^\s\n]+)', re.IGNORECASE),
        re.compile(r'No match for argument:\s+([^\s\n]+)', re.IGNORECASE),
        re.compile(r'No package\s+([^\s\n]+)\s+available', re.IGNORECASE),
        re.compile(r'Could not find a package for:\s*([^\s]+)', re.IGNORECASE),
    ]

    bootc_builder = True

    probe_command = ShellScript(
        """
        type dnf && ((dnf --version | grep -E 'dnf5 version') && exit 1 || exit 0)
        """
    ).to_shell_command()
    # The priority of preference: `rpm-ostree` > `dnf5` > `dnf` > `yum`.
    # `rpm-ostree` has its own implementation and its own priority, and
    # the `dnf` family just stays below it.
    probe_priority = 50

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        try:
            output = self.guest.execute(self.engine.check_presence(*installables))
            stdout = output.stdout

        except RunError as exc:
            stdout = exc.stdout

        if stdout is None:
            raise GeneralError("rpm presence check provided no output")

        results: dict[Installable, bool] = {}

        for line, installable in zip(stdout.strip().splitlines(), installables):
            # Match for packages not installed, when "rpm -q PACKAGE" used
            match = re.match(rf'package {re.escape(str(installable))} is not installed', line)
            if match is not None:
                results[installable] = False
                continue

            # Match for provided rpm capabilities (packages, commands, etc.),
            # when "rpm -q --whatprovides CAPABILITY" used
            match = re.match(rf'no package provides {re.escape(str(installable))}', line)
            if match is not None:
                results[installable] = False
                continue

            # Match for filesystem paths, when "rpm -q --whatprovides PATH" used
            match = re.match(
                rf'error: file {re.escape(str(installable))}: No such file or directory', line
            )
            if match is not None:
                results[installable] = False
                continue

            results[installable] = True

        return results

    def _enable_copr_epel6(self, copr: str) -> None:
        """
        Manually enable copr repositories for epel6
        """

        url = build_copr_repo_url(copr, 'epel-6')
        # Download the repo file on guest
        try:
            self.guest.execute(
                Command('curl', '-LOf', url),
                cwd=Path('/etc/yum.repos.d'),
                silent=True,
            )
        except RunError as error:
            if error.stderr and 'not found' in error.stderr.lower():
                raise PrepareError(f"Copr repository '{copr}' not found.") from error
            raise

    def enable_copr(self, *repositories: str) -> None:
        """
        Enable requested copr repositories
        """

        if not repositories:
            return

        # Try to install copr plugin
        self.debug('Make sure the copr plugin is available.')
        try:
            self.install(Package(self.copr_plugin))

        # Enable repositories manually for epel6
        except RunError:
            for repository in repositories:
                self.info('copr', repository, 'green')
                self._enable_copr_epel6(repository)

        # Enable repositories using copr plugin
        else:
            for repository in repositories:
                self.info('copr', repository, 'green')
                self.guest.execute(
                    ShellScript(
                        f"{self.engine.command.to_script()} copr "
                        f"{self.engine.options.to_script()} enable -y {repository}"
                    )
                )

    def install_local(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:

        options = options or Options()
        options.check_first = False
        # Use both install/reinstall to get all packages refreshed
        # FIXME Simplify this once BZ#1831022 is fixed/implemented.
        output = self.install(*installables, options=options)
        self.reinstall(*installables, options=options)
        return output

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:

        output = super().install_debuginfo(*installables, options=options)

        # Check the packages are installed because 'debuginfo-install'
        # returns 0 even though it didn't manage to install the required packages
        if not (options and options.skip_missing):
            self.check_presence(*[Package(f'{p}-debuginfo') for p in installables])
        return output


class Dnf5Engine(DnfEngine):
    _base_command = Command('dnf5')
    _base_debuginfo_command = Command('dnf5', 'debuginfo-install')
    skip_missing_packages_option = '--skip-unavailable'
    skip_missing_debuginfo_option = skip_missing_packages_option


@provides_package_manager('dnf5')
class Dnf5(Dnf):
    NAME = 'dnf5'

    _engine_class = Dnf5Engine

    copr_plugin: ClassVar[str] = 'dnf5-command(copr)'

    probe_command = Command('dnf5', '--version')
    probe_priority = 60


class YumEngine(DnfEngine):
    _base_command = Command('yum')

    # TODO: get rid of those `type: ignore` below. I think it's caused by the
    # decorator, it might be messing with the class inheritance as seen by pyright,
    # but mypy sees no issue, pytest sees no issue, everything works. Silencing
    # for now.
    def install(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        script = cast(  # type: ignore[redundant-cast]
            ShellScript,
            self._construct_install_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                *installables, options=options
            ),
        )

        # Extra ignore/check for yum to workaround BZ#1920176
        if options.skip_missing:
            script |= ShellScript('/bin/true')

        else:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables
                ),
            )

        return script

    def reinstall(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        script = cast(  # type: ignore[redundant-cast]
            ShellScript,
            self._construct_reinstall_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                *installables, options=options
            ),
        )

        # Extra ignore/check for yum to workaround BZ#1920176
        if options.skip_missing:
            script |= ShellScript('/bin/true')

        else:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables
                ),
            )

        return script

    def refresh_metadata(self) -> ShellScript:
        return ShellScript(f'{self.command.to_script()} makecache')


@provides_package_manager('yum')
class Yum(Dnf):
    NAME = 'yum'

    _engine_class = YumEngine

    copr_plugin: ClassVar[str] = 'yum-plugin-copr'

    bootc_builder = False

    probe_command = ShellScript(
        """
        type yum && ((yum --version | grep -E 'dnf5 version') && exit 1 || exit 0)
        """
    ).to_shell_command()
    probe_priority = 40
