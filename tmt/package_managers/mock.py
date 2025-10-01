from typing import (
    Optional,
)

from tmt.package_managers import (
    Installable,
    Options,
    PackageManager,
    PackageManagerEngine,
    escape_installables,
    provides_package_manager,
)
from tmt.steps.provision import Guest
from tmt.steps.provision.mock import GuestMock
from tmt.utils import Command, CommandOutput, RunError, ShellScript


class BaseMockEngine(PackageManagerEngine):
    """
    We use `mock --pm-cmd ...` to execute the package manager commands inside
    the mock. Such scripts need to be executed locally and not inside the mock
    shell. To differentiate these scripts we set a special attribute `_local`
    of the script object.
    """

    def _prepare_mock_command_script(self, script: str) -> ShellScript:
        return ShellScript(f'{self.command} {self.options.to_script()} {script}')

    def _prepare_mock_install_script(
        self,
        installword: str,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()
        extra_options = Command()

        for package in options.excluded_packages:
            extra_options += Command('--exclude', package)

        if options.skip_missing:
            extra_options += Command('--skip-broken')

        return self._prepare_mock_command_script(
            f'{installword} {extra_options} {" ".join(escape_installables(*installables))}'
        )

    def prepare_command(self) -> tuple[Command, Command]:
        options = Command()
        assert isinstance(self.guest, GuestMock)
        if self.guest.root is not None:
            options += Command('-r', self.guest.root)
        options += Command('--pm-cmd')
        return (Command('mock'), options)

    def check_presence(self, *installables: Installable) -> ShellScript:
        return ShellScript(f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}')

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._prepare_mock_install_script('install', *installables, options=options)

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._prepare_mock_install_script('reinstall', *installables, options=options)

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._prepare_mock_install_script(
            'debuginfo-install', *installables, options=options
        )

    def refresh_metadata(self) -> ShellScript:
        return self._prepare_mock_command_script('makecache --refresh')


class MockYumEngine(BaseMockEngine):
    pass


class MockDnfEngine(BaseMockEngine):
    pass


class MockDnf5Engine(BaseMockEngine):
    pass


class BaseMock:
    probe_command = Command('/usr/bin/false')
    probe_priority = 130
    guest: Guest
    engine: PackageManagerEngine

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        if options is not None and options.check_first:
            try:
                return self.guest.execute(self.engine.check_presence(*installables))
            except RunError:
                pass
        return self.guest.run(
            self.engine.install(*installables, options=options).to_shell_command()
        )

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        if options is not None and options.check_first:
            try:
                return self.guest.execute(self.engine.check_presence(*installables))
            except RunError:
                pass
        return self.guest.run(
            self.engine.reinstall(*installables, options=options).to_shell_command()
        )

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        if options is not None and options.check_first:
            try:
                return self.guest.execute(self.engine.check_presence(*installables))
            except RunError:
                pass
        return self.guest.run(
            self.engine.install_debuginfo(*installables, options=options).to_shell_command()
        )

    def refresh_metadata(self) -> CommandOutput:
        return self.guest.run(self.engine.refresh_metadata().to_shell_command())


# ignore[type-arg]: Follow the rest of package managers
@provides_package_manager('mock-yum')
class MockYum(BaseMock, PackageManager[MockYumEngine]):
    NAME = 'mock-yum'
    _engine_class = MockYumEngine


# ignore[type-arg]: Follow the rest of package managers
@provides_package_manager('mock-dnf')
class MockDnf(BaseMock, PackageManager[MockDnfEngine]):
    NAME = 'mock-dnf'
    _engine_class = MockDnfEngine


# ignore[type-arg]: Follow the rest of package managers
@provides_package_manager('mock-dnf5')
class MockDnf5(BaseMock, PackageManager[MockDnf5Engine]):
    NAME = 'mock-dnf5'
    _engine_class = MockDnf5Engine
