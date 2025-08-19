"""
Custom tmt sphinx extensions
"""

import datetime
import functools
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sphinx.application import Sphinx

# custom linkcheck cache variables
linkcheck_cache_period = 1.0


def generate_tmt_docs(app: "Sphinx", config: Any) -> None:
    """
    Run `make generate` to populate the auto-generated sources
    """

    conf_dir = Path(app.confdir)
    subprocess.run(["make", "generate"], cwd=conf_dir, check=True)


@functools.cache
def get_web_git_url(app: "Sphinx") -> str:
    from tmt.log import Logger
    from tmt.utils.git import GitInfo, web_git_url

    gitinfo = GitInfo.from_fmf_root(
        fmf_root=app.srcdir.parent,
        logger=Logger.get_bootstrap_logger(),
    )
    return web_git_url(gitinfo.url, gitinfo.ref)


def linkcheck_check_cache(app: "Sphinx", uri: str) -> str | None:
    # Get the cache result files
    cache_file = app.outdir / "linkcheck_cache.json"
    now = datetime.datetime.now(datetime.UTC)
    cache_file.touch()
    with cache_file.open("rt") as f:
        try:
            cache_data = json.load(f)
        except json.JSONDecodeError:
            cache_data = {}

    # Redirect paths pointing to the current git tree to filepaths
    web_git_url = get_web_git_url(app)
    if uri.startswith(web_git_url):
        path = uri.removeprefix(web_git_url)
        return str(app.srcdir.parent / path.lstrip("/"))

    # Check if we have cached this uri yet
    if uri in cache_data:
        # Check if the cache data is recent enough
        cached_time = datetime.datetime.fromtimestamp(cache_data[uri], datetime.UTC)
        age = now - cached_time
        if age < datetime.timedelta(days=linkcheck_cache_period):
            # cache is relatively recent, so we skip this uri
            return str(cache_file.absolute())
    # If either check fails, we want to do the check and update the cache
    cache_data[uri] = now.timestamp()
    with cache_file.open("wt") as f:
        json.dump(cache_data, f)
    return uri


def setup(app: "Sphinx") -> None:
    # Generate sources after loading configuration. That should build
    # everything, including the logo, before Sphinx starts checking
    # whether all input files exist.
    app.connect("config-inited", generate_tmt_docs)
    # Check a cached version of the linkcheck results
    app.connect("linkcheck-process-uri", linkcheck_check_cache)
