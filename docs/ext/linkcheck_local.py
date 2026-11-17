"""
Sphinx extension to redirect git urls to local files
"""

import functools
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sphinx.application import Sphinx


@functools.cache
def get_web_git_url(app: "Sphinx") -> str:
    from tmt.log import Logger
    from tmt.utils.git import GitInfo, web_git_url

    gitinfo = GitInfo.from_fmf_root(
        fmf_root=app.srcdir.parent,
        logger=Logger.get_bootstrap_logger(),
    )
    return web_git_url(gitinfo.url, gitinfo.ref)


def linkcheck_local(app: "Sphinx", uri: str) -> Optional[str]:
    """
    Redirect paths pointing to the current git tree to filepaths.
    """
    web_git_url = get_web_git_url(app)
    if uri.startswith(web_git_url):
        path = uri.removeprefix(web_git_url)
        return str(app.srcdir.parent / path.lstrip("/"))
    return uri


def setup(app: "Sphinx"):
    app.connect("linkcheck-process-uri", linkcheck_local)
