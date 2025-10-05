"""Unit tests for the repository artifact provider using pytest."""

from shlex import quote
from unittest.mock import MagicMock, call

import pytest

from tmt.steps.prepare.artifact.providers.repository import (
    DownloadError,
    GeneralError,
    RepositoryFileProvider,
    RepositoryManager,
)
from tmt.utils import Path, ShellScript


@pytest.fixture
def mock_logger():
    """Provides a MagicMock for the logger."""
    return MagicMock()


@pytest.fixture
def mock_guest():
    """Provides a MagicMock for the guest."""
    guest = MagicMock()
    guest.facts.is_superuser = False
    return guest


class TestRepositoryManager:
    """Tests for the RepositoryManager utility class."""

    def test_enable_repository_success(self, mock_guest, mock_logger):
        """Test successful repository enabling."""
        url = "http://example.com/my.repo"
        filename = "my.repo"
        repo_dest = Path("/etc/yum.repos.d") / filename

        path = RepositoryManager.enable_repository(mock_guest, url, filename, mock_logger)

        assert path == repo_dest
        # The implementation uses shlex.quote, so the expected script must match exactly.
        command = f"sudo curl -L --fail -o {quote(str(repo_dest))} {quote(url)}"

        mock_guest.execute.assert_called_once()
        actual_script = mock_guest.execute.call_args[0][0]
        assert isinstance(actual_script, ShellScript)
        assert str(actual_script) == command
        assert mock_guest.execute.call_args[1] == {'silent': True}

    def test_enable_repository_fails(self, mock_guest, mock_logger):
        """Test repository enabling when curl fails."""
        mock_guest.execute.side_effect = GeneralError("curl failed")
        with pytest.raises(DownloadError, match="Failed to download repository file"):
            RepositoryManager.enable_repository(
                mock_guest, "http://example.com/my.repo", "my.repo", mock_logger
            )

    def test_get_repository_id_success(self, mock_guest, mock_logger):
        """Test successful extraction of a repository ID."""
        mock_result = MagicMock()
        mock_result.stdout = "my-repo-id\n"
        mock_guest.execute.return_value = mock_result
        repo_filepath = Path("/etc/yum.repos.d/my.repo")

        repo_id = RepositoryManager.get_repository_id(mock_guest, repo_filepath, mock_logger)

        assert repo_id == "my-repo-id"
        command = (
            f"grep '^\\[' {quote(str(repo_filepath))} | head -n 1 | sed 's/^\\[\\(.*\\)\\]$/\\1/'"
        )

        mock_guest.execute.assert_called_once()
        actual_script = mock_guest.execute.call_args[0][0]
        assert isinstance(actual_script, ShellScript)
        assert str(actual_script) == command
        assert mock_guest.execute.call_args[1] == {'silent': True}

    def test_get_repository_id_fails(self, mock_guest, mock_logger):
        """Test failure when repository ID cannot be found."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_guest.execute.return_value = mock_result
        repo_filepath = Path("/etc/yum.repos.d/my.repo")

        with pytest.raises(GeneralError, match="Could not extract repository ID"):
            RepositoryManager.get_repository_id(mock_guest, repo_filepath, mock_logger)

    def test_fetch_rpms_success(self, mock_guest, mock_logger):
        """Test successfully fetching and parsing RPM list."""
        repo_filepath = Path("/etc/yum.repos.d/my.repo")
        repo_id = "my-repo-id"
        # Mock repo ID and dnf query calls
        mock_repo_id_output = MagicMock()
        mock_repo_id_output.stdout = repo_id
        mock_dnf_output = MagicMock()
        mock_dnf_output.stdout = "package1 (none) 1.0 1.el8 noarch\npackage2 1 2.0 2.el8 x86_64\n"
        mock_guest.execute.side_effect = [mock_repo_id_output, mock_dnf_output]

        rpms = RepositoryManager.fetch_rpms(mock_guest, repo_filepath, mock_logger)

        assert len(rpms) == 2
        assert rpms[0].id == "package1-1.0-1.el8.noarch.rpm"
        assert rpms[1].id == "package2-1:2.0-2.el8.x86_64.rpm"

        qf = "'%{name} %{epoch} %{version} %{release} %{arch}'"

        assert mock_guest.execute.call_count == 2
        calls = mock_guest.execute.call_args_list

        # Verify first call (get_repository_id)
        command = (
            f"grep '^\\[' {quote(str(repo_filepath))} | head -n 1 | sed 's/^\\[\\(.*\\)\\]$/\\1/'"
        )
        assert str(calls[0][0][0]) == command

        # Verify second call (dnf repoquery)
        command = (
            "dnf repoquery --refresh --disablerepo='*' "
            f"--enablerepo={quote(repo_id)} --available "
            f"--queryformat {qf}"
        )
        assert str(calls[1][0][0]) == command


class TestRepositoryFileProvider:
    """Tests for the RepositoryFileProvider class."""

    def test_init_valid_url(self, mock_logger):
        """Test successful initialization with a valid URL."""
        provider = RepositoryFileProvider(
            raw_provider_id="http://example.com/repo.repo", logger=mock_logger
        )
        assert provider.id == "http://example.com/repo.repo"
        assert provider.repo_filename == "repo.repo"

    @pytest.mark.parametrize(
        "invalid_url", ["invalid-url", "/path/to/file.repo", "http:/missing-slash.com/repo.repo"]
    )
    def test_init_invalid_url(self, invalid_url, mock_logger):
        """Test that initialization fails with invalid URLs."""
        with pytest.raises(GeneralError, match="Invalid URL format"):
            RepositoryFileProvider(raw_provider_id=invalid_url, logger=mock_logger)

    def test_artifacts_before_fetch(self, mock_logger):
        """Artifacts should fail if fetch_contents has not been called."""
        provider = RepositoryFileProvider(
            raw_provider_id="http://example.com/repo.repo", logger=mock_logger
        )
        with pytest.raises(GeneralError, match="RPM list not available"):
            list(provider.artifacts)

    def test_download_artifact_raises_not_implemented(self, mock_guest, mock_logger):
        """_download_artifact should always raise NotImplementedError."""
        provider = RepositoryFileProvider(
            raw_provider_id="http://example.com/repo.repo", logger=mock_logger
        )
        with pytest.raises(NotImplementedError):
            provider._download_artifact(MagicMock(), mock_guest, Path("/tmp/dest"))

    def test_fetch_contents_success(self, mock_guest, mock_logger):
        """Test a successful fetch_contents run."""
        provider = RepositoryFileProvider(
            raw_provider_id="http://example.com/my.repo", logger=mock_logger
        )

        repo_dest = Path('/etc/yum.repos.d/my.repo')
        repo_url = 'http://example.com/my.repo'
        repo_id = "my-repo-id"
        qf = "'%{name} %{epoch} %{version} %{release} %{arch}'"

        # Mock the outputs of guest.execute
        mock_repo_id_output = MagicMock()
        mock_repo_id_output.stdout = repo_id
        mock_dnf_output = MagicMock()
        mock_dnf_output.stdout = "package1 (none) 1.0 1.el8 noarch\npackage2 1 2.0 2.el8 x86_64\n"
        mock_guest.execute.side_effect = [
            MagicMock(),  # curl for enable_repository
            mock_repo_id_output,  # grep for get_repository_id
            mock_dnf_output,  # dnf repoquery for fetch_rpms
        ]

        # Run fetch_contents
        result_paths = provider.fetch_contents(mock_guest, Path("/tmp/download"))
        assert result_paths == []  # Should return empty list

        # Verify calls to guest.execute
        assert mock_guest.execute.call_count == 3
        calls = mock_guest.execute.call_args_list

        # 1. Verify curl call
        command = f"sudo curl -L --fail -o {quote(str(repo_dest))} {quote(repo_url)}"
        assert str(calls[0][0][0]) == command

        # 2. Verify grep call
        command = (
            f"grep '^\\[' {quote(str(repo_dest))} | head -n 1 | sed 's/^\\[\\(.*\\)\\]$/\\1/'"
        )
        assert str(calls[1][0][0]) == command

        # 3. Verify dnf call
        command = (
            "dnf repoquery --refresh --disablerepo='*' "
            f"--enablerepo={quote(repo_id)} --available "
            f"--queryformat {qf}"
        )
        assert str(calls[2][0][0]) == command

        # Verify the artifact list is populated correctly
        artifacts = list(provider.artifacts)
        assert len(artifacts) == 2
        assert artifacts[0].id == "package1-1.0-1.el8.noarch.rpm"
        assert artifacts[1].id == "package2-1:2.0-2.el8.x86_64.rpm"
