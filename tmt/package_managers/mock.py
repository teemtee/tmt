import tmt.package_managers.dnf
from tmt.package_managers import (
    PackageManager,
    provides_package_manager,
)
from tmt.utils import (
    Command,
)


class MockYumEngine(tmt.package_managers.dnf.YumEngine):
    pass


class MockDnfEngine(tmt.package_managers.dnf.DnfEngine):
    pass


class MockDnf5Engine(tmt.package_managers.dnf.Dnf5Engine):
    pass


class BaseMock:
    probe_command = Command("false")
    probe_priority = 130


@provides_package_manager('mock-yum')
class MockYum(BaseMock, PackageManager[MockYumEngine]):
    NAME = 'mock-yum'
    _engine_class = MockYumEngine


@provides_package_manager('mock-dnf')
class MockDnf(BaseMock, PackageManager[MockDnfEngine]):
    NAME = 'mock-dnf'
    _engine_class = MockDnfEngine


@provides_package_manager('mock-dnf5')
class MockDnf5(BaseMock, PackageManager[MockDnf5Engine]):
    NAME = 'mock-dnf5'
    _engine_class = MockDnf5Engine
