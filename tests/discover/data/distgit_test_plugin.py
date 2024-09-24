
import urllib.parse

from tmt.utils import DistGitHandler, Path

MOCK_SOURCES_FILENAME = 'mock_sources'
SERVER_PORT = 9000


class TestDistGit(DistGitHandler):
    """
    Test handler

    each line in MOCK_SOURCES_FILENAME contains
    filename to serve and optional (after single space a custom filename)
    """

    usage_name = "TESTING"
    server = f"http://localhost:{SERVER_PORT}"

    def url_and_name(self, cwd=None):
        cwd = cwd or Path.cwd()
        data = (cwd / MOCK_SOURCES_FILENAME).read_text()
        for line in data.splitlines():
            split = line.split(' ', maxsplit=2)
            url = split[0]
            try:
                src_name = split[1]
            except IndexError:
                src_name = url

            yield (urllib.parse.urljoin(self.server, url), src_name)
