import pytest

from tmt.steps.prepare.artifact.providers.repository import RepositoryFile
from tmt.utils import GeneralError


@pytest.mark.parametrize(
    ("url", "expected_filename"),
    [
        ("http://example.com/my.repo", "my.repo"),
        ("https://domain.org/path/to/another-repo.repo", "another-repo.repo"),
        ("https://a.b.c/d/e/f/g/h/i/j.repo", "j.repo"),
        (
            "http://example.com/path/with%20spaces/file%20with%20spaces.repo",
            "file with spaces.repo",
        ),
        ("http://example.com/some-repo", "some-repo"),
    ],
)
def test_valid_url(url, expected_filename):
    """Test that a valid URL is parsed correctly."""
    repo_file = RepositoryFile(url=url)
    assert repo_file.url == url
    assert repo_file.filename == expected_filename


@pytest.mark.parametrize(
    "invalid_url",
    [
        "not-a-url",
        "www.example.com/my.repo",  # Missing scheme
        "http://",  # Missing network location
        "https//example.com/my.repo",  # Malformed scheme
    ],
)
def test_invalid_url(invalid_url):
    """Test that an invalid URL raises GeneralError."""
    with pytest.raises(GeneralError, match=f"Invalid URL format for .repo file: '{invalid_url}'"):
        RepositoryFile(url=invalid_url)


def test_filename_extraction_with_query_params():
    """Test filename extraction from a URL with query parameters."""
    url = "http://example.com/my.repo?foo=bar&baz=qux"
    repo_file = RepositoryFile(url=url)
    assert repo_file.filename == "my.repo"


def test_filename_with_special_chars():
    """Test filename with special characters that get unquoted."""
    url = "https://example.com/repos/my%2Bspecial%26repo.repo"
    repo_file = RepositoryFile(url=url)
    assert repo_file.filename == "my+special&repo.repo"
