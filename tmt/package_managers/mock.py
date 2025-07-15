from typing import Optional

from tmt.package_managers import (
    Installable,
    Options,
    PackageManager,
    PackageManagerEngine,
    provides_package_manager,
)
from tmt.utils import (
    Command,
    CommandOutput,
)


class MockEngine(PackageManagerEngine):
    def prepare_command(self) -> tuple[Command, Command]:
        # NOTE package installation is handled completely outside of the guest
        return (None, None)


@provides_package_manager('mock')
class Mock(PackageManager[MockEngine]):
    NAME = 'mock'

    _engine_class = MockEngine

    probe_command = Command("false")

    # needs to be larger than priorities of `yum`, `dnf`, `dnf5` and `rpm-ostree`.
    probe_priority = 130

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        # NOTE possible via execute `rpm -q --whatprovides`?
        raise NotImplementedError

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        self.guest.mock_shell.install(*list(map(str, installables)), options=options)

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        # NOTE is this even possible in mock?
        raise NotImplementedError

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        raise NotImplementedError

    def refresh_metadata(self) -> CommandOutput:
        # noop
        return CommandOutput(stdout="", stderr="")
