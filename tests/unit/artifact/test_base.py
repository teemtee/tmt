import re
from unittest.mock import MagicMock

import pytest

import tmt.utils
from tmt.base.core import DependencySimple
from tmt.steps.prepare.artifact import ARTIFACT_SHARED_REPO_NAME, PrepareArtifact
from tmt.steps.prepare.artifact.providers import ArtifactInfo, ArtifactProvider, Version


class MockProvider(ArtifactProvider):
    def _extract_provider_id(self, raw_id: str) -> str:
        return raw_id.split(":", 1)[1]

    @property
    def artifacts(self):
        return [
            ArtifactInfo(
                version=Version(name="mock", version="1.0", release="1", arch="x86_64"),
                location="http://example.com/mock-1.0-1.x86_64.rpm",
                provider=self,
            )
        ]

    def _download_artifact(self, artifact, guest, destination):
        destination.write_text("ok")

    def contribute_to_shared_repo(
        self, guest, source_path, shared_repo_dir, exclude_patterns=None
    ):
        pass


@pytest.fixture
def mock_provider(root_logger):
    return MockProvider("mock:123", repository_priority=50, logger=root_logger)


def test_filter_artifacts(mock_provider):
    artifacts = list(mock_provider._filter_artifacts([re.compile("mock")]))
    assert artifacts == []


def test_download_artifacts(tmp_path, root_logger, mock_provider):
    guest = MagicMock()

    paths = mock_provider.fetch_contents(guest, tmp_path, [])
    file_path = tmp_path / "mock-1.0-1.x86_64.rpm"
    assert file_path in paths
    assert file_path.exists()
    assert file_path.read_text() == "ok"


def test_persist_artifact_metadata(tmp_path, mock_provider):
    prepare = MagicMock()
    prepare.plan_workdir = tmp_path
    prepare.ARTIFACTS_METADATA_FILENAME = 'artifacts.yaml'
    prepare.data.auto_verify = True

    PrepareArtifact._detect_duplicate_nvras(prepare, mock_provider, {})
    PrepareArtifact._save_artifacts_metadata(prepare, [mock_provider])

    # Verify YAML
    yaml_file = tmp_path / "artifacts.yaml"
    assert yaml_file.exists()

    content = tmt.utils.from_yaml(yaml_file.read_text())

    assert len(content["providers"]) == 1

    provider_data = content["providers"][0]
    assert provider_data["id"] == "mock:123"
    assert provider_data["auto_verify"] is True
    assert len(provider_data["artifacts"]) == 1

    artifact = provider_data["artifacts"][0]
    expected = {
        "version": {
            "name": "mock",
            "version": "1.0",
            "release": "1",
            "arch": "x86_64",
            "epoch": 0,
        },
        "nvra": "mock-1.0-1.x86_64",
        "location": "http://example.com/mock-1.0-1.x86_64.rpm",
    }
    assert artifact == expected


def test_duplicate_nvra_detection(tmp_path, root_logger):
    # Two providers with the same NVRA
    provider1 = MockProvider("mock:provider1", repository_priority=50, logger=root_logger)
    provider2 = MockProvider("mock:provider2", repository_priority=50, logger=root_logger)

    prepare = MagicMock()
    prepare.plan_workdir = tmp_path

    seen_nvras = {}

    # First one should succeed
    PrepareArtifact._detect_duplicate_nvras(prepare, provider1, seen_nvras)
    assert "mock-1.0-1.x86_64" in seen_nvras
    assert seen_nvras["mock-1.0-1.x86_64"] == "mock:provider1"

    # Second one with same NVRA should raise error
    with pytest.raises(
        tmt.utils.PrepareError,
        match=(
            r"Artifact 'mock-1\.0-1\.x86_64' provided by both "
            r"'mock:provider1' and 'mock:provider2'"
        ),
    ):
        PrepareArtifact._detect_duplicate_nvras(prepare, provider2, seen_nvras)


# ---------------------------------------------------------------------------
# _populate_verify_from_providers
# ---------------------------------------------------------------------------


def _make_guest() -> MagicMock:
    """Return a mock guest where all tests are considered enabled."""
    guest = MagicMock()
    guest.name = 'test-guest'
    return guest


def _make_prepare_for_verify(
    root_logger,
    test_require: list[str] | None = None,
    install_packages: list[str] | None = None,
    guest: MagicMock | None = None,
    test_enabled_on_guest: bool = True,
) -> MagicMock:
    """
    Build a minimal PrepareArtifact mock wired up for verify-population tests.

    Uses a plain MagicMock (no spec) so that instance attributes like `step`
    which are set at runtime (not declared as class attributes) are accessible.

    :param test_enabled_on_guest: Controls the return value of
        ``test.enabled_on_guest()``.  Set to ``False`` to simulate a test that
        is not scheduled on the given guest.
    """
    prepare = MagicMock()
    prepare._future_verify = MagicMock()
    prepare._future_verify.data.verify = {}

    # Wire test require/recommend from discover
    test_obj = MagicMock()
    test_obj.require = [DependencySimple(p) for p in (test_require or [])]
    test_obj.recommend = []
    test_obj.enabled_on_guest.return_value = test_enabled_on_guest
    test_origin = MagicMock()
    test_origin.test = test_obj
    prepare.step.plan.discover.tests.return_value = [test_origin]

    # Wire explicit install phases
    install_phase = MagicMock()
    install_phase.data.package = [DependencySimple(p) for p in (install_packages or [])]
    prepare.step.phases.return_value = [install_phase]

    return prepare


def test_populate_verify_package_in_artifact_and_require(root_logger):
    """Package present in both artifact and test require → added to verify dict."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    prepare = _make_prepare_for_verify(root_logger, test_require=["mock"])

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    assert prepare._future_verify.data.verify == {"mock": ARTIFACT_SHARED_REPO_NAME}


def test_populate_verify_package_in_artifact_only(root_logger):
    """Package in artifact but not in any requirement → NOT added to verify dict."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    prepare = _make_prepare_for_verify(root_logger, test_require=[])

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    assert prepare._future_verify.data.verify == {}


def test_populate_verify_package_in_require_only(root_logger):
    """Package in requirements but not in artifact → NOT added to verify dict."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    prepare = _make_prepare_for_verify(root_logger, test_require=["other-package"])

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    assert prepare._future_verify.data.verify == {}


def test_populate_verify_package_in_artifact_and_install_phase(root_logger):
    """Package in artifact and explicit install phase → added to verify dict."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    prepare = _make_prepare_for_verify(root_logger, install_packages=["mock"])

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    assert prepare._future_verify.data.verify == {"mock": ARTIFACT_SHARED_REPO_NAME}


def test_populate_verify_no_future_verify(root_logger):
    """When _future_verify is None (verify=False), dict is never touched."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    prepare = MagicMock()
    prepare._future_verify = None

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    # Method should return early without error
    assert prepare._future_verify is None


def test_populate_verify_empty_intersection(root_logger):
    """No overlap between artifact packages and requirements → verify dict stays empty."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    prepare = _make_prepare_for_verify(root_logger, test_require=["gcc", "make"])

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    assert prepare._future_verify.data.verify == {}


def test_populate_verify_guest_filtering(root_logger):
    """Test only enabled on a different guest does NOT contribute its packages to verify."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    # Simulate test NOT enabled on this guest
    prepare = _make_prepare_for_verify(
        root_logger,
        test_require=["mock"],
        test_enabled_on_guest=False,
    )

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    # "mock" is in artifact but the test providing it is not on this guest → empty
    assert prepare._future_verify.data.verify == {}


def test_populate_verify_debug_logs_uncovered_packages(root_logger):
    """Packages in require but not in artifact emit a debug log (not a hard error)."""
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)
    guest = _make_guest()
    # "mock" matches, "gcc" does not → intersection = {"mock"}, uncovered = {"gcc"}
    prepare = _make_prepare_for_verify(root_logger, test_require=["mock", "gcc"])

    PrepareArtifact._populate_verify_from_providers(prepare, [provider], guest)

    assert prepare._future_verify.data.verify == {"mock": ARTIFACT_SHARED_REPO_NAME}
    # self.debug() must have been called at least once (for the uncovered package note)
    assert prepare.debug.called
