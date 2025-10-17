import hashlib
from unittest.mock import MagicMock, patch

import pytest

import tmt.log
from tmt.steps.prepare.artifact.providers import Repository
from tmt.utils import GeneralError, Path, requests

# A valid .repo file content for testing, using Docker CE repo
VALID_REPO_CONTENT = """
[docker-ce-stable]
name=Docker CE Stable - $basearch
baseurl=https://download.docker.com/linux/centos/$releasever/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://download.docker.com/linux/centos/gpg

[docker-ce-test]
name=Docker CE Test - $basearch
baseurl=https://download.docker.com/linux/centos/$releasever/$basearch/test
enabled=0
gpgcheck=1
gpgkey=https://download.docker.com/linux/centos/gpg

[docker-ce-nightly]
name=Docker CE Nightly - $basearch
baseurl=https://download.docker.com/linux/centos/$releasever/$basearch/nightly
enabled=0
gpgcheck=1
gpgkey=https://download.docker.com/linux/centos/gpg
"""

# Expected repository IDs from the valid content
EXPECTED_REPO_IDS = ["docker-ce-stable", "docker-ce-test", "docker-ce-nightly"]

# Malformed content for error handling tests
MALFORMED_REPO_CONTENT = """
[my-repo
name=Missing closing bracket
"""


# Mock logger fixture for all tests
@pytest.fixture
def logger():
    """Provides a tmt logger for tests"""
    return tmt.log.Logger.create()


# Fixture to create a temporary .repo file
@pytest.fixture
def temp_repo_file(tmp_path):
    """Creates a temporary repo file with valid content"""
    repo_file = tmp_path / "docker-ce.repo"
    repo_file.write_text(VALID_REPO_CONTENT)
    return repo_file


def test_init_from_content(logger):
    """Test successful initialization from a content string"""
    repo = Repository(logger=logger, name="from-content", content=VALID_REPO_CONTENT)
    assert repo.name == "from-content"
    assert repo.content == VALID_REPO_CONTENT
    assert repo.repo_ids == EXPECTED_REPO_IDS
    assert repo.filename == "from-content.repo"


def test_init_from_file(logger, temp_repo_file):
    """Test successful initialization from a local file path"""
    repo = Repository(logger=logger, file_path=temp_repo_file)
    assert repo.name == "docker-ce"
    assert repo.content == VALID_REPO_CONTENT
    assert repo.repo_ids == EXPECTED_REPO_IDS


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_init_from_url(mock_retry_session, logger):
    """Test successful initialization from a URL"""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    repo_url = "https://download.docker.com/linux/centos/docker-ce.repo"
    repo = Repository(logger=logger, url=repo_url)

    assert repo.name == "docker-ce"
    assert repo.content == VALID_REPO_CONTENT
    assert repo.repo_ids == EXPECTED_REPO_IDS
    mock_session.get.assert_called_once_with(repo_url)


def test_init_no_source_fails(logger):
    """Test that initialization fails if no source is provided"""
    with pytest.raises(GeneralError, match="Repository content could not be loaded"):
        Repository(logger=logger)


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_name_derivation(mock_retry_session, logger, temp_repo_file):
    """Test the logic for deriving the repository name"""
    # Provided name takes precedence
    repo = Repository(logger=logger, name="explicit-name", content="[foo]")
    assert repo.name == "explicit-name"

    # Mock the session for the URL test
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "[foo]"
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    # Name derived from URL
    repo = Repository(logger=logger, url="http://a.b/c/docker-ce.repo")
    assert repo.name == "docker-ce"

    # Name derived from file path
    repo = Repository(logger=logger, file_path=temp_repo_file)
    assert repo.name == "docker-ce"

    # Fallback name
    repo = Repository(logger=logger, content="[foo]")
    assert repo.name.startswith("repo-")


def test_repo_id_parsing(logger):
    """Test the parsing of repo IDs from content"""
    # Valid content with multiple sections
    repo = Repository(logger=logger, content=VALID_REPO_CONTENT)
    assert repo.repo_ids == EXPECTED_REPO_IDS

    # Content with no sections is invalid for configparser
    with pytest.raises(GeneralError, match=r"The .repo file may be malformed"):
        Repository(logger=logger, content="name=No sections here\nenabled=1")

    # Malformed content should also raise an error
    with pytest.raises(GeneralError, match=r"The .repo file may be malformed"):
        Repository(logger=logger, content=MALFORMED_REPO_CONTENT)


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_deterministic_id(mock_retry_session, logger):
    """Test that the generated ID is deterministic"""
    repo_content = "[docker-ce-stable]\nname=Docker CE Stable"
    # Mock the session for URL tests
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = repo_content
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    repo_url = "http://example.com/docker.repo"

    # Same URL should produce the same ID
    repo1_url = Repository(logger=logger, url=repo_url)
    repo2_url = Repository(logger=logger, url=repo_url)
    assert repo1_url.id == repo2_url.id

    # Same content should produce the same ID
    repo1_content = Repository(logger=logger, name="same-name", content=repo_content)
    repo2_content = Repository(logger=logger, name="same-name", content=repo_content)
    assert repo1_content.id == repo2_content.id

    # Different sources should produce different IDs
    assert repo1_url.id != repo1_content.id


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_failed_url_fetch(mock_retry_session, logger):
    """Test that a failed URL fetch raises an error"""
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.RequestException("Connection failed")
    mock_retry_session.return_value.__enter__.return_value = mock_session

    with pytest.raises(GeneralError, match="Failed to fetch repository content"):
        Repository(logger=logger, url="http://example.com/invalid.repo")


def test_nonexistent_file(logger):
    """Test that a non-existent file path raises an error"""
    with pytest.raises(GeneralError, match="Failed to read repository file"):
        Repository(logger=logger, file_path=Path("/no/such/file.repo"))
