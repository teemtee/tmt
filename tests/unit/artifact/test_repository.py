from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare.artifact.providers import Repository
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.prepare.artifact.providers.repository import (
    RepositoryFileProvider,
    parse_rpm_string,
)
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


@pytest.mark.parametrize(
    ("pkg_string", "expected"),
    [
        # With epoch
        (
            "docker-ce-1:20.10.7-3.el8.x86_64",
            {
                "name": "docker-ce",
                "epoch": "1",
                "version": "20.10.7",
                "release": "3.el8",
                "arch": "x86_64",
                "nvr": "docker-ce-20.10.7-3.el8",
            },
        ),
        # Without epoch
        (
            "bash-5.1.8-6.el9.x86_64",
            {
                "name": "bash",
                "epoch": "0",
                "version": "5.1.8",
                "release": "6.el9",
                "arch": "x86_64",
                "nvr": "bash-5.1.8-6.el9",
            },
        ),
        # Name with '+', version with '+' and '.', release with '.'
        (
            "tmt+export-polarion-1.61.0.dev17+gf29b2e83e-1.fc41.x86_64",
            {
                "name": "tmt+export-polarion",
                "epoch": "0",
                "version": "1.61.0.dev17+gf29b2e83e",
                "release": "1.fc41",
                "arch": "x86_64",
                "nvr": "tmt+export-polarion-1.61.0.dev17+gf29b2e83e-1.fc41",
            },
        ),
        # Name with multiple '-', no epoch
        (
            "keylime-agent-rust-push-debuginfo-0.2.3-1.fc41.x86_64",
            {
                "name": "keylime-agent-rust-push-debuginfo",
                "epoch": "0",
                "version": "0.2.3",
                "release": "1.fc41",
                "arch": "x86_64",
                "nvr": "keylime-agent-rust-push-debuginfo-0.2.3-1.fc41",
            },
        ),
        # With epoch 0 explicitly
        (
            "example-0:1.0-1.noarch",
            {
                "name": "example",
                "epoch": "0",
                "version": "1.0",
                "release": "1",
                "arch": "noarch",
                "nvr": "example-1.0-1",
            },
        ),
    ],
)
def test_parse_rpm_string_valid(pkg_string, expected):
    result = parse_rpm_string(pkg_string)
    assert result == expected


@pytest.mark.parametrize(
    "pkg_string",
    [
        "invalid-string",  # No match
        "name-version.x86_64",  # Missing release
        "name-1:version.x86_64",  # Missing release
        "name-version-release",  # Missing arch
        "name-version-release.x86.64",  # Dot in arch
        "name-version--release.x86_64",  # Double '-'
        "name-a:b-release.x86_64",  # Invalid epoch (not digit before :)
        "name-1:ver-sion-release.x86_64",  # '-' in version
        "name-version-rel-ease.x86_64",  # '-' in release
    ],
)
def test_parse_rpm_string_invalid(pkg_string):
    with pytest.raises(ValueError, match=r"does not match|Malformed package string"):
        parse_rpm_string(pkg_string)


# ================================================================================
# Tests for RepositoryFileProvider
# ================================================================================


def test_repository_provider_id_extraction(root_logger):
    """Test provider ID extraction from raw provider ID"""

    # Valid provider ID
    raw_id = "repository-url:https://download.docker.com/linux/centos/docker-ce.repo"
    provider = RepositoryFileProvider(raw_id, root_logger)
    assert provider.id == "https://download.docker.com/linux/centos/docker-ce.repo"


def test_repository_provider_invalid_format(root_logger):
    """Test that invalid provider ID formats raise ValueError"""

    # Missing prefix
    with pytest.raises(ValueError, match="Invalid repository provider format"):
        RepositoryFileProvider("https://example.com/repo.repo", root_logger)

    # Empty URL after prefix
    with pytest.raises(ValueError, match="Missing repository URL"):
        RepositoryFileProvider("repository-url:", root_logger)


def test_repository_provider_artifacts_before_fetch(root_logger):
    """Test that accessing artifacts before fetch_contents raises error"""

    provider = RepositoryFileProvider("repository-url:https://example.com/test.repo", root_logger)

    with pytest.raises(GeneralError, match="Call fetch_contents first"):
        _ = provider.artifacts


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_repository_provider_fetch_contents(mock_retry_session, root_logger):
    """Test fetch_contents method discovers RPMs from repository"""

    # Mock the Repository.from_url call
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    # Mock guest and package manager
    mock_guest = MagicMock()
    mock_package_manager = MagicMock()
    mock_guest.package_manager = mock_package_manager

    # Mock list_packages to return some RPMs
    mock_package_manager.list_packages.return_value = [
        "docker-ce-1:20.10.7-3.el8.x86_64",
        "docker-ce-cli-1:20.10.7-3.el8.x86_64",
        "containerd.io-1.4.6-3.1.el8.x86_64",
    ]

    provider = RepositoryFileProvider(
        "repository-url:https://download.docker.com/linux/centos/docker-ce.repo", root_logger
    )

    # Call fetch_contents
    result = provider.fetch_contents(mock_guest, Path("/tmp/artifacts"))

    # Verify result is empty list (discovery-only provider)
    assert result == []

    # Verify package manager methods were called
    mock_package_manager.install_repository.assert_called_once()
    mock_package_manager.list_packages.assert_called_once()

    # Verify artifacts property now works
    artifacts = provider.artifacts
    assert len(artifacts) == 3
    assert artifacts[0]._raw_artifact["name"] == "docker-ce"
    assert artifacts[0]._raw_artifact["version"] == "20.10.7"
    assert artifacts[0]._raw_artifact["epoch"] == "1"
    assert artifacts[0]._raw_artifact["release"] == "3.el8"
    assert artifacts[0]._raw_artifact["arch"] == "x86_64"


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_repository_provider_malformed_packages(mock_retry_session, root_logger):
    """Test that malformed package strings are skipped with warnings"""

    # Mock the Repository.from_url call
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    # Mock guest and package manager
    mock_guest = MagicMock()
    mock_package_manager = MagicMock()
    mock_guest.package_manager = mock_package_manager

    # Mock list_packages with mix of valid and malformed packages
    mock_package_manager.list_packages.return_value = [
        "docker-ce-1:20.10.7-3.el8.x86_64",  # Valid
        "invalid-package-string",  # Invalid - no arch
        "bash-5.1.8-6.el9.x86_64",  # Valid
        "another-malformed",  # Invalid
    ]

    provider = RepositoryFileProvider("repository-url:https://example.com/test.repo", root_logger)

    # Call fetch_contents
    provider.fetch_contents(mock_guest, Path("/tmp/artifacts"))

    # Verify only valid packages were added
    artifacts = provider.artifacts
    assert len(artifacts) == 2
    assert artifacts[0]._raw_artifact["name"] == "docker-ce"
    assert artifacts[1]._raw_artifact["name"] == "bash"


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_repository_provider_empty_repository(mock_retry_session, root_logger):
    """Test handling of repository with no packages"""

    # Mock the Repository.from_url call
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    # Mock guest and package manager
    mock_guest = MagicMock()
    mock_package_manager = MagicMock()
    mock_guest.package_manager = mock_package_manager

    # Mock list_packages to return empty list
    mock_package_manager.list_packages.return_value = []

    provider = RepositoryFileProvider("repository-url:https://example.com/test.repo", root_logger)

    # Call fetch_contents
    provider.fetch_contents(mock_guest, Path("/tmp/artifacts"))

    # Verify artifacts is empty but accessible
    artifacts = provider.artifacts
    assert len(artifacts) == 0


@patch('tmt.steps.prepare.artifact.providers.tmt.utils.retry_session')
def test_repository_provider_unexpected_error_handling(mock_retry_session, root_logger):
    """Test handling of unexpected errors during package parsing"""

    # Mock the Repository.from_url call
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = VALID_REPO_CONTENT
    mock_response.raise_for_status.return_value = None
    mock_session.get.return_value = mock_response
    mock_retry_session.return_value.__enter__.return_value = mock_session

    # Mock guest and package manager
    mock_guest = MagicMock()
    mock_package_manager = MagicMock()
    mock_guest.package_manager = mock_package_manager

    # Mock list_packages to return packages
    mock_package_manager.list_packages.return_value = [
        "docker-ce-1:20.10.7-3.el8.x86_64",
    ]

    provider = RepositoryFileProvider("repository-url:https://example.com/test.repo", root_logger)

    # Patch parse_rpm_string to raise an unexpected exception
    with patch(
        'tmt.steps.prepare.artifact.providers.repository.parse_rpm_string',
        side_effect=RuntimeError("Unexpected error"),
    ):
        # Should not raise, but log warning
        provider.fetch_contents(mock_guest, Path("/tmp/artifacts"))

        # Artifacts should be empty since parsing failed
        artifacts = provider.artifacts
        assert len(artifacts) == 0
