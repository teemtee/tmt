from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare.artifact.providers import Repository
from tmt.steps.prepare.artifact.providers.repository import parse_rpm_string
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


# Tests for create_repository function
def test_create_repository_success(root_logger):
    """Test successful repository creation from artifact directory"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import CommandOutput

    # Mock guest
    mock_guest = MagicMock()
    # Only one execute() call: directory existence check (test -d)
    mock_guest.execute.return_value = CommandOutput(stdout="", stderr="")  # test -d succeeds
    # Mock the package manager's create_repository_metadata_from_dir method
    mock_guest.package_manager.create_repository_metadata_from_dir.return_value = None

    artifact_dir = Path("/tmp/my-artifacts")

    # Call create_repository
    repo = create_repository(
        artifact_dir=artifact_dir, guest=mock_guest, logger=root_logger, repo_name="my-repo"
    )

    # Verify the guest.execute was called once (for test -d)
    assert mock_guest.execute.call_count == 1
    # Verify the package manager method was called
    mock_guest.package_manager.create_repository_metadata_from_dir.assert_called_once_with(
        artifact_dir
    )

    # Verify the repository was created correctly
    assert repo.name == "my-repo"
    assert "my-repo" in repo.content
    assert f"baseurl=file://{artifact_dir}" in repo.content
    assert "priority=99" in repo.content
    assert "enabled=1" in repo.content
    assert "gpgcheck=0" in repo.content
    assert repo.repo_ids == ["my-repo"]


def test_create_repository_auto_name(root_logger):
    """Test repository creation with automatic name derivation"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import CommandOutput

    # Mock guest
    mock_guest = MagicMock()
    mock_guest.execute.side_effect = [
        CommandOutput(stdout="", stderr=""),  # test -d succeeds
        CommandOutput(stdout="Repository created", stderr=""),  # createrepo_c succeeds
    ]

    artifact_dir = Path("/tmp/koji-artifacts")

    # Call create_repository without repo_name
    repo = create_repository(artifact_dir=artifact_dir, guest=mock_guest, logger=root_logger)

    # Verify the name was derived from directory
    assert repo.name == "koji-artifacts"
    assert "koji-artifacts" in repo.content


def test_create_repository_directory_not_exists(root_logger):
    """Test repository creation fails when directory doesn't exist"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import Command, RunError

    # Mock guest
    mock_guest = MagicMock()
    # test -d fails (directory doesn't exist)
    mock_guest.execute.side_effect = RunError(
        "Directory not found", Command("test", "-d"), returncode=1
    )

    artifact_dir = Path("/tmp/nonexistent")

    # Verify it raises GeneralError
    with pytest.raises(GeneralError, match=r"Artifact directory .* does not exist on guest"):
        create_repository(artifact_dir=artifact_dir, guest=mock_guest, logger=root_logger)


def test_create_repository_createrepo_fails(root_logger):
    """Test repository creation fails when createrepo_c fails"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import CommandOutput

    # Mock guest
    mock_guest = MagicMock()
    # First call succeeds (dir exists)
    mock_guest.execute.return_value = CommandOutput(stdout="", stderr="")  # test -d succeeds
    # Package manager method fails
    mock_guest.package_manager.create_repository_metadata_from_dir.side_effect = GeneralError(
        "createrepo_c failed"
    )

    artifact_dir = Path("/tmp/bad-artifacts")

    # Verify it raises GeneralError
    with pytest.raises(GeneralError, match=r"Failed to create repository metadata"):
        create_repository(artifact_dir=artifact_dir, guest=mock_guest, logger=root_logger)


def test_create_repository_empty_name(root_logger):
    """Test repository creation fails with empty directory name"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository

    # Mock guest
    mock_guest = MagicMock()

    # Use root path which has empty name
    artifact_dir = Path("/")

    # Verify it raises GeneralError
    with pytest.raises(GeneralError, match=r"Could not derive repository name"):
        create_repository(artifact_dir=artifact_dir, guest=mock_guest, logger=root_logger)


def test_create_repository_custom_priority(root_logger):
    """Test repository creation with custom priority value"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import CommandOutput

    # Mock guest
    mock_guest = MagicMock()
    mock_guest.execute.return_value = CommandOutput(stdout="", stderr="")
    mock_guest.package_manager.create_repository_metadata_from_dir.return_value = None

    artifact_dir = Path("/tmp/my-artifacts")

    # Call create_repository with custom priority
    repo = create_repository(
        artifact_dir=artifact_dir,
        guest=mock_guest,
        logger=root_logger,
        repo_name="custom-repo",
        priority=50,
    )

    # Verify the custom priority is in the content
    assert "priority=50" in repo.content
    assert repo.name == "custom-repo"


def test_create_repository_special_chars_in_name(root_logger):
    """Test repository creation sanitizes special characters in repo name"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import CommandOutput

    # Mock guest
    mock_guest = MagicMock()
    mock_guest.execute.return_value = CommandOutput(stdout="", stderr="")
    mock_guest.package_manager.create_repository_metadata_from_dir.return_value = None

    artifact_dir = Path("/tmp/my artifacts")

    # Call create_repository with name containing spaces
    repo = create_repository(
        artifact_dir=artifact_dir,
        guest=mock_guest,
        logger=root_logger,
        repo_name="my special repo!",
    )

    # Verify the name was sanitized (tmt.utils.sanitize_name should be used)
    # The sanitized name should be in the content as the repo ID
    # (spaces->hyphens, special chars removed)
    assert "[my-special-repo]" in repo.content
    # Verify the original name is preserved in the name field
    assert repo.name == "my special repo!"
    # Verify the sanitized version is the repo_id
    assert repo.repo_ids == ["my-special-repo"]


def test_create_repository_installs_on_guest(root_logger):
    """Test that create_repository calls install_repository on the guest"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import CommandOutput

    # Mock guest
    mock_guest = MagicMock()
    mock_guest.execute.return_value = CommandOutput(stdout="", stderr="")
    mock_guest.package_manager.create_repository_metadata_from_dir.return_value = None

    artifact_dir = Path("/tmp/my-artifacts")

    # Call create_repository
    repo = create_repository(
        artifact_dir=artifact_dir, guest=mock_guest, logger=root_logger, repo_name="test-repo"
    )

    # Verify install_repository was called
    mock_guest.package_manager.install_repository.assert_called_once()
    # Verify it was called with the created repository
    installed_repo = mock_guest.package_manager.install_repository.call_args[0][0]
    assert installed_repo.name == repo.name
    assert installed_repo.content == repo.content


def test_create_repository_not_implemented_error(root_logger):
    """Test repository creation when package manager doesn't support it"""
    from tmt.steps.prepare.artifact.providers.repository import create_repository
    from tmt.utils import CommandOutput

    # Mock guest
    mock_guest = MagicMock()
    mock_guest.execute.return_value = CommandOutput(stdout="", stderr="")
    # Package manager doesn't support creating repositories
    mock_guest.package_manager.create_repository_metadata_from_dir.side_effect = (
        NotImplementedError("Not supported")
    )

    artifact_dir = Path("/tmp/my-artifacts")

    # Verify it raises GeneralError
    with pytest.raises(GeneralError, match=r"Failed to create repository metadata"):
        create_repository(artifact_dir=artifact_dir, guest=mock_guest, logger=root_logger)


# Tests for DnfEngine.create_repository_metadata_from_dir
def test_dnf_create_repository_metadata_createrepo_already_installed(root_logger):
    """Test DNF metadata creation when createrepo is already installed"""
    from tmt.package_managers.dnf import DnfEngine
    from tmt.utils import Command, CommandOutput

    # Mock guest and engine
    mock_guest = MagicMock()
    engine = DnfEngine(guest=mock_guest, logger=root_logger)

    # Mock that createrepo is found
    mock_guest.execute.side_effect = [
        CommandOutput(stdout="/usr/bin/createrepo\n", stderr=""),  # command -v createrepo
        CommandOutput(stdout="Repository created", stderr=""),  # createrepo execution
    ]

    directory = Path("/tmp/packages")

    # Call the method
    engine.create_repository_metadata_from_dir(directory)

    # Verify execute was called twice: once to find createrepo, once to run it
    assert mock_guest.execute.call_count == 2
    # Verify the second call was to run createrepo
    second_call_args = mock_guest.execute.call_args_list[1]
    assert str(directory) in str(second_call_args[0][0])


def test_dnf_create_repository_metadata_createrepo_needs_install(root_logger):
    """Test DNF metadata creation when createrepo needs to be installed"""
    from tmt.package_managers.dnf import DnfEngine
    from tmt.utils import Command, CommandOutput, RunError

    # Mock guest and engine
    mock_guest = MagicMock()
    engine = DnfEngine(guest=mock_guest, logger=root_logger)

    # Mock the flow: createrepo not found, install it, then find it, then run it
    mock_guest.execute.side_effect = [
        RunError("not found", Command("command", "-v", "createrepo"), returncode=1),  # Not found
        CommandOutput(stdout="Installed", stderr=""),  # Installation command
        CommandOutput(stdout="/usr/bin/createrepo\n", stderr=""),  # command -v after install
        CommandOutput(stdout="Repository created", stderr=""),  # createrepo execution
    ]

    directory = Path("/tmp/packages")

    # Call the method
    engine.create_repository_metadata_from_dir(directory)

    # Verify install was called
    # The install method should have been called
    assert mock_guest.execute.call_count == 4


def test_dnf_create_repository_metadata_install_fails(root_logger):
    """Test DNF metadata creation when createrepo installation fails"""
    from tmt.package_managers.dnf import DnfEngine
    from tmt.utils import Command, RunError

    # Mock guest and engine
    mock_guest = MagicMock()
    engine = DnfEngine(guest=mock_guest, logger=root_logger)

    # Mock: createrepo not found, installation fails
    mock_guest.execute.side_effect = [
        RunError("not found", Command("command", "-v", "createrepo"), returncode=1),  # Not found
        RunError("install failed", Command("dnf", "install"), returncode=1),  # Install fails
    ]

    directory = Path("/tmp/packages")

    # Verify it raises GeneralError
    with pytest.raises(GeneralError, match=r"Prerequisite 'createrepo' not found"):
        engine.create_repository_metadata_from_dir(directory)


def test_dnf_create_repository_metadata_execution_fails(root_logger):
    """Test DNF metadata creation when createrepo execution fails"""
    from tmt.package_managers.dnf import DnfEngine
    from tmt.utils import Command, CommandOutput, RunError

    # Mock guest and engine
    mock_guest = MagicMock()
    engine = DnfEngine(guest=mock_guest, logger=root_logger)

    # Mock: createrepo found but execution fails
    mock_guest.execute.side_effect = [
        CommandOutput(stdout="/usr/bin/createrepo\n", stderr=""),  # command -v succeeds
        RunError("execution failed", Command("createrepo"), returncode=1),  # Execution fails
    ]

    directory = Path("/tmp/packages")

    # Verify it raises GeneralError
    with pytest.raises(GeneralError, match=r"Failed to create repository metadata"):
        engine.create_repository_metadata_from_dir(directory)


def test_dnf_create_repository_metadata_empty_stdout(root_logger):
    """Test DNF metadata creation handles empty stdout from command -v"""
    from tmt.package_managers.dnf import DnfEngine
    from tmt.utils import CommandOutput

    # Mock guest and engine
    mock_guest = MagicMock()
    engine = DnfEngine(guest=mock_guest, logger=root_logger)

    # Mock: command -v returns empty stdout (edge case)
    mock_guest.execute.side_effect = [
        CommandOutput(stdout="", stderr=""),  # Empty stdout
        CommandOutput(stdout="Repository created", stderr=""),  # createrepo execution
    ]

    directory = Path("/tmp/packages")

    # Call the method - it should handle empty stdout gracefully
    engine.create_repository_metadata_from_dir(directory)

    # Verify the createrepo was still called (with empty string path)
    assert mock_guest.execute.call_count == 2


# Tests for base PackageManager
def test_package_manager_base_create_repository_not_implemented(root_logger):
    """Test that base PackageManager raises NotImplementedError"""
    from tmt.package_managers import PackageManagerEngine
    from tmt.utils import Command

    # Create a minimal concrete implementation that doesn't override
    # create_repository_metadata_from_dir
    class MinimalPackageManagerEngine(PackageManagerEngine):
        _base_command = Command('test-pm')

        def install(self, *args, **kwargs):
            return Command('echo', 'install')

        def reinstall(self, *args, **kwargs):
            return Command('echo', 'reinstall')

        def install_debuginfo(self, *args, **kwargs):
            return Command('echo', 'install-debuginfo')

        def check_presence(self, *args, **kwargs):
            return Command('echo', 'check')

        def refresh_metadata(self, *args, **kwargs):
            return Command('echo', 'refresh')

        def prepare_command(self, *args, **kwargs):
            return (Command('test-pm'), Command('--options'))

    # Create a minimal mock guest
    mock_guest = MagicMock()

    # Create engine instance
    engine = MinimalPackageManagerEngine(guest=mock_guest, logger=root_logger)

    directory = Path("/tmp/packages")

    # Verify it raises NotImplementedError since we didn't override the method
    with pytest.raises(NotImplementedError):
        engine.create_repository_metadata_from_dir(directory)
