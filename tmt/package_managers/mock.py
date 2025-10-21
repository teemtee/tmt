import re
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
from tmt.steps.provision.mock import GuestMock
from tmt.utils import Command, CommandOutput, GeneralError, RunError, ShellScript


class MockEngine(PackageManagerEngine):
    """
    We use `mock --pm-cmd ...` to execute the package manager commands inside
    the mock. Such scripts need to be executed locally and not inside the mock
    shell.
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


class _MockPackageManager(PackageManager[MockEngine]):
    probe_command = Command('/usr/bin/false')
    probe_priority = 130
    _engine_class = MockEngine

    # Implementation "stolen" from the dnf package manager family. It should
    # be good enough for mock, at least for now.
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
            # TODO implement a more robust check that the package is not installed
            # other than catching RunError.
            try:
                self.guest.execute(self.engine.check_presence(*installables))
            except RunError as err:
                return err.output
        return self.guest.run(
            self.engine.reinstall(*installables, options=options).to_shell_command()
        )

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        return self.guest.run(
            self.engine.install_debuginfo(*installables, options=options).to_shell_command()
        )

    def refresh_metadata(self) -> CommandOutput:
        return self.guest.run(self.engine.refresh_metadata().to_shell_command())


# ignore[type-arg]: TypeVar in package manager registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_package_manager('mock-yum')  # type: ignore[arg-type]
class MockYum(_MockPackageManager):
    NAME = 'mock-yum'


# ignore[type-arg]: TypeVar in package manager registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_package_manager('mock-dnf')  # type: ignore[arg-type]
class MockDnf(_MockPackageManager):
    NAME = 'mock-dnf'


# ignore[type-arg]: TypeVar in package manager registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_package_manager('mock-dnf5')  # type: ignore[arg-type]
class MockDnf5(_MockPackageManager):
    NAME = 'mock-dnf5'
