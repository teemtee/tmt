import re
from unittest.mock import MagicMock

from tmt.steps.prepare.artifact.providers import ArtifactInfo, ArtifactProvider, Version


class MockProvider(ArtifactProvider):
    def _extract_provider_id(self, raw_provider_id: str) -> str:
        return raw_provider_id.split(":", 1)[1]

    def get_installable_artifacts(self):
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


def test_filter_artifacts(root_logger):
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)

    artifacts = list(provider._filter_artifacts([re.compile("mock")]))
    assert artifacts == []


def test_download_artifacts(tmp_path, root_logger):
    guest = MagicMock()
    provider = MockProvider("mock:123", repository_priority=50, logger=root_logger)

    paths = provider.fetch_contents(guest, tmp_path, [])
    file_path = tmp_path / "123-mock-1.0-1.x86_64.rpm"
    assert file_path in paths
    assert file_path.exists()
    assert file_path.read_text() == "ok"
