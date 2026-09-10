"""
Sphinx extension to cache linkcheck results
"""

import datetime
import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sphinx.application import Sphinx


def linkcheck_cache(app: "Sphinx", uri: str) -> Optional[str]:
    # Get the cache result files
    cache_file = app.outdir / "linkcheck_cache.json"
    now = datetime.datetime.now(datetime.UTC)
    cache_file.touch()
    with cache_file.open("rt") as f:
        try:
            cache_data = json.load(f)
        except json.JSONDecodeError:
            cache_data = {}

    # Check if we have cached this uri yet
    if uri in cache_data:
        # Check if the cache data is recent enough
        cached_time = datetime.datetime.fromtimestamp(cache_data[uri], datetime.UTC)
        age = now - cached_time
        if age < datetime.timedelta(days=app.config["linkcheck_cache_period"]):
            # cache is relatively recent, so we skip this uri
            return str(cache_file.absolute())
    # If either check fails, we want to do the check and update the cache
    cache_data[uri] = now.timestamp()
    with cache_file.open("wt") as f:
        json.dump(cache_data, f)
    return uri


def setup(app: "Sphinx"):
    app.connect("linkcheck-process-uri", linkcheck_cache)
    app.add_config_value(
        "linkcheck_cache_period",
        default=1.0,
        types=float,
        rebuild="",
        description="How long should the linkchecks results be cached for.",
    )
