from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare.artifact.providers import Repository
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
def temp_repo_file(tmppath):
    """Creates a temporary repo file with valid content"""
    repo_file = tmppath / "docker-ce.repo"
    repo_file.write_text(VALID_REPO_CONTENT)
    return repo_file


@pytest.fixture
def temp_repo_file_no_ext(tmppath):
    """Creates a temporary repo file without .repo extension"""
    repo_file = tmppath / "docker-ce"
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
        # Example of src rpm
        (
            "example-5.1.8-6.el9.src",
            {
                "name": "example",
                "epoch": "0",
                "version": "5.1.8",
                "release": "6.el9",
                "arch": "src",
                "nvr": "example-5.1.8-6.el9",
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


@pytest.fixture
def mock_repo_file_fetch():
    with patch(
        'tmt.steps.prepare.artifact.providers.tmt.utils.retry_session'
    ) as mock_retry_session:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = VALID_REPO_CONTENT
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_retry_session.return_value.__enter__.return_value = mock_session
        yield mock_session


@pytest.fixture
def mock_guest_and_pm():
    mock_guest = MagicMock()
    mock_package_manager = MagicMock()
    mock_guest.package_manager = mock_package_manager
    return mock_guest, mock_package_manager


def test_id_extraction(root_logger):
    """Test provider ID extraction from raw provider ID"""

    # Valid provider ID
    raw_id = "repository-url:https://download.docker.com/linux/centos/docker-ce.repo"
    provider = RepositoryFileProvider(raw_id, root_logger)
    assert provider.id == "https://download.docker.com/linux/centos/docker-ce.repo"


def test_artifacts_before_fetch(mock_repo_file_fetch, root_logger):
    """Test that accessing artifacts before fetch_contents raises error"""

    provider = RepositoryFileProvider("repository-url:https://example.com/test.repo", root_logger)

    with pytest.raises(
        GeneralError,
        match=r"Call fetch_contents",
    ):
        _ = provider.artifacts


def test_fetch_contents(mock_repo_file_fetch, mock_guest_and_pm, root_logger, tmppath):
    """Test fetch_contents method discovers RPMs from repository"""

    mock_guest, mock_package_manager = mock_guest_and_pm

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
    # Note: fetch_contents expects the repository to already be installed by PrepareArtifact
    artifacts_dir = tmppath / "artifacts"
    result = provider.fetch_contents(mock_guest, artifacts_dir)

    # Verify result is empty list (discovery-only provider)
    assert result == []

    # Verify list_packages was called (to discover packages from the already-installed repo)
    mock_package_manager.list_packages.assert_called_once()

    # Verify artifacts property now works
    artifacts = provider.artifacts
    assert len(artifacts) == 3

    # Verify all expected packages are present
    artifact_names = {a._raw_artifact["name"] for a in artifacts}
    assert artifact_names == {"docker-ce", "docker-ce-cli", "containerd.io"}

    # Verify docker-ce artifact properties
    docker_ce = next(a for a in artifacts if a._raw_artifact["name"] == "docker-ce")
    assert docker_ce._raw_artifact["version"] == "20.10.7"
    assert docker_ce._raw_artifact["epoch"] == "1"
    assert docker_ce._raw_artifact["release"] == "3.el8"
    assert docker_ce._raw_artifact["arch"] == "x86_64"


def test_malformed_packages(mock_repo_file_fetch, mock_guest_and_pm, root_logger, tmppath, caplog):
    """Test that malformed package strings are skipped with warnings"""

    mock_guest, mock_package_manager = mock_guest_and_pm

    # Mock list_packages with mix of valid and malformed packages
    mock_package_manager.list_packages.return_value = [
        "docker-ce-1:20.10.7-3.el8.x86_64",  # Valid
        "invalid-package-string",  # Invalid - no arch
        "bash-5.1.8-6.el9.x86_64",  # Valid
        "another-malformed",  # Invalid
    ]

    provider = RepositoryFileProvider("repository-url:https://example.com/test.repo", root_logger)

    # Call fetch_contents
    artifacts_dir = tmppath / "artifacts"
    provider.fetch_contents(mock_guest, artifacts_dir)

    artifacts = provider.artifacts
    assert len(artifacts) == 2
    artifact_names = {a._raw_artifact["name"] for a in artifacts}
    assert artifact_names == {"docker-ce", "bash"}

    # Check logs for warnings about invalid packages
    assert (
        "Failed to parse malformed package string 'invalid-package-string'. Skipping."
        in caplog.text
    )
    assert "String 'invalid-package-string' does not match N-E:V-R.A format" in caplog.text
    assert "Failed to parse malformed package string 'another-malformed'. Skipping." in caplog.text
    assert "String 'another-malformed' does not match N-E:V-R.A format" in caplog.text


def test_empty_repository(mock_repo_file_fetch, mock_guest_and_pm, root_logger, tmppath):
    """Test handling of repository with no packages"""

    mock_guest, mock_package_manager = mock_guest_and_pm

    # Mock list_packages to return empty list
    mock_package_manager.list_packages.return_value = []

    provider = RepositoryFileProvider("repository-url:https://example.com/test.repo", root_logger)

    # Call fetch_contents
    artifacts_dir = tmppath / "artifacts"
    provider.fetch_contents(mock_guest, artifacts_dir)

    # Verify artifacts is empty but accessible
    artifacts = provider.artifacts
    assert len(artifacts) == 0


def test_unexpected_error_handling(
    mock_repo_file_fetch, mock_guest_and_pm, root_logger, tmppath, caplog
):
    """Test handling of unexpected errors during package parsing"""

    mock_guest, mock_package_manager = mock_guest_and_pm

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
        artifacts_dir = tmppath / "artifacts"
        provider.fetch_contents(mock_guest, artifacts_dir)

        # Artifacts should be empty since parsing failed
        artifacts = provider.artifacts
        assert len(artifacts) == 0

        # Check log for warning about unexpected error
        assert "Unexpected error" in caplog.text


def test_contribute_to_shared_repo(mock_repo_file_fetch, mock_guest_and_pm, root_logger, tmppath):
    """Test that contribute_to_shared_repo does nothing for repository providers"""

    mock_guest, mock_package_manager = mock_guest_and_pm

    # Mock list_packages to return some RPMs
    mock_package_manager.list_packages.return_value = [
        "docker-ce-1:20.10.7-3.el8.x86_64",
        "docker-ce-cli-1:20.10.7-3.el8.x86_64",
    ]

    provider = RepositoryFileProvider(
        "repository-url:https://download.docker.com/linux/centos/docker-ce.repo", root_logger
    )

    # Call contribute_to_shared_repo
    # Repository providers don't contribute files to the shared repo,
    # they just provide Repository objects via get_repositories()
    artifacts_dir = tmppath / "artifacts"
    shared_repo_dir = tmppath / "shared"
    provider.contribute_to_shared_repo(mock_guest, artifacts_dir, shared_repo_dir)

    # Verify no package manager methods were called (since contribute_to_shared_repo is a no-op)
    mock_package_manager.install_repository.assert_not_called()
    mock_package_manager.list_packages.assert_not_called()

    # Verify artifacts were not discovered yet (fetch_contents hasn't been called)
    with pytest.raises(GeneralError, match=r"Call fetch_contents"):
        _ = provider.artifacts
