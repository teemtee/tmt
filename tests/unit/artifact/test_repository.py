from unittest.mock import MagicMock, patch

import pytest

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
[my-repo]
name
"""

NO_SECTION_CONTENT = "name=No sections here\nenabled=1"


# Fixture to create a temporary .repo file
@pytest.fixture
def temp_repo_file(tmp_path):
    """Creates a temporary repo file with valid content"""
    repo_file = tmp_path / "docker-ce.repo"
    repo_file.write_text(VALID_REPO_CONTENT)
    return repo_file


@pytest.fixture
def temp_repo_file_no_ext(tmp_path):
    """Creates a temporary repo file without .repo extension"""
    repo_file = tmp_path / "docker-ce"
    repo_file.write_text(VALID_REPO_CONTENT)
    return repo_file


def test_init_from_content(root_logger):
    """Test successful initialization from a content string"""
    repo = Repository.from_content(
        name="from-content", content=VALID_REPO_CONTENT, logger=root_logger
    )
    assert repo.name == "from-content"
    assert repo.content == VALID_REPO_CONTENT
    assert repo.repo_ids == EXPECTED_REPO_IDS
    assert repo.filename == "from-content.repo"


def test_init_from_file(temp_repo_file, root_logger):
    """Test successful initialization from a local file path"""
    repo = Repository.from_file_path(file_path=temp_repo_file, logger=root_logger)
    assert repo.name == "docker-ce"
    assert repo.content == VALID_REPO_CONTENT
    assert repo.repo_ids == EXPECTED_REPO_IDS


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_init_from_url(mock_retry_session, root_logger):
    """Test successful initialization from a URL"""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    repo_url = "https://download.docker.com/linux/centos/docker-ce.repo"
    repo = Repository.from_url(url=repo_url, logger=root_logger)

    assert repo.name == "docker-ce"
    assert repo.content == VALID_REPO_CONTENT
    assert repo.repo_ids == EXPECTED_REPO_IDS
    mock_session.get.assert_called_once_with(repo_url)


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_name_derivation(mock_retry_session, temp_repo_file, root_logger):
    """Test the logic for deriving the repository name"""
    # Provided name takes precedence
    repo = Repository.from_content(name="explicit-name", content="[foo]", logger=root_logger)
    assert repo.name == "explicit-name"

    # Mock the session for the URL test
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "[foo]"
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    # Name derived from URL
    repo = Repository.from_url(url="http://a.b/c/docker-ce.repo", logger=root_logger)
    assert repo.name == "docker-ce"

    # Name derived from file path
    repo = Repository.from_file_path(file_path=temp_repo_file, logger=root_logger)
    assert repo.name == "docker-ce"


def test_repo_id_parsing(root_logger):
    """Test the parsing of repo IDs from content"""
    # Valid content with multiple sections
    repo = Repository.from_content(name="valid", content=VALID_REPO_CONTENT, logger=root_logger)
    assert repo.repo_ids == EXPECTED_REPO_IDS

    # Content with no sections (empty)
    with pytest.raises(GeneralError, match="No repository sections found"):
        Repository.from_content(name="no-sections", content="", logger=root_logger)

    # Content with options but no section header
    with pytest.raises(GeneralError, match="No repository sections found"):
        Repository.from_content(name="no-sections", content=NO_SECTION_CONTENT, logger=root_logger)

    # Malformed content should also raise an error
    with pytest.raises(GeneralError, match=r"The .repo file may be malformed"):
        Repository.from_content(
            name="malformed", content=MALFORMED_REPO_CONTENT, logger=root_logger
        )


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_failed_url_fetch(mock_retry_session, root_logger):
    """Test that a failed URL fetch raises an error"""
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.RequestException("Connection failed")
    mock_retry_session.return_value.__enter__.return_value = mock_session

    with pytest.raises(GeneralError, match="Failed to fetch repository content"):
        Repository.from_url(url="http://example.com/invalid.repo", logger=root_logger)


def test_nonexistent_file(root_logger):
    """Test that a non-existent file path raises an error"""
    with pytest.raises(GeneralError, match="Failed to read repository file"):
        Repository.from_file_path(file_path=Path("/no/such/file.repo"), logger=root_logger)


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_url_trailing_slash(mock_retry_session, root_logger):
    """Test URL with trailing slash"""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    repo = Repository.from_url(url="https://example.com/repo/", logger=root_logger)
    assert repo.name == "repo"


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_url_no_repo_ext(mock_retry_session, root_logger):
    """Test URL without .repo extension"""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    repo = Repository.from_url(url="https://example.com/docker-ce", logger=root_logger)
    assert repo.name == "docker-ce"


def test_file_no_repo_ext(temp_repo_file_no_ext, root_logger):
    """Test file without .repo extension"""
    repo = Repository.from_file_path(file_path=temp_repo_file_no_ext, logger=root_logger)
    assert repo.name == "docker-ce"


def test_content_no_name(root_logger):
    """Test content without name raises error"""
    with pytest.raises(GeneralError, match="Repository name cannot be empty"):
        Repository.from_content(content=VALID_REPO_CONTENT, name="", logger=root_logger)


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_invalid_url_format(mock_retry_session, root_logger):
    """Test initialization with invalid URL format"""
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.InvalidURL("Invalid URL")
    mock_retry_session.return_value.__enter__.return_value = mock_session

    with pytest.raises(GeneralError, match="Failed to fetch repository content"):
        Repository.from_url(url="invalid_url", logger=root_logger)


def test_url_no_path(root_logger):
    """Test URL with no path raises error"""
    with patch(
        'tmt.steps.prepare.artifact.providers.tmt.utils.retry_session'
    ) as mock_retry_session:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = VALID_REPO_CONTENT
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_retry_session.return_value.__enter__.return_value = mock_session

        with pytest.raises(GeneralError, match="Could not derive repository name from URL"):
            Repository.from_url(url="https://example.com/", logger=root_logger)
