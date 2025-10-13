import pytest

from tmt.steps.prepare.artifact.providers.brew import BrewArtifactProvider


@pytest.mark.integration
def test_brew_valid_build(root_logger):
    provider = BrewArtifactProvider("brew.build:3866328", root_logger)
    assert len(provider.artifacts) == 21
