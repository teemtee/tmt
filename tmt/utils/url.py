"""
Url handling helpers.
"""

import re

import tmt.log
import tmt.utils
from tmt.utils import Path


def download(url: str, destination: Path, *, logger: tmt.log.Logger) -> Path:
    logger.debug(f"Downloading '{url}'.")
    with tmt.utils.retry_session(logger=logger) as session:
        response = session.get(url, stream=True)
    response.raise_for_status()
    if destination.is_dir():
        if "Content-Disposition" in response.headers:
            match = re.findall("filename=(.+)", response.headers["Content-Disposition"])
            if not match:
                raise tmt.utils.GeneralError("Could not determine filename from header")
            file_name = match[0]
        else:
            file_name = response.url.split("/")[-1]
    else:
        if destination.exists():
            raise tmt.utils.GeneralError(f"Destination file already exists: {destination}")
        file_name = destination.name
        destination = destination.parent
    assert isinstance(file_name, str)  # Narrow type
    download_file = destination / file_name
    download_file.write_bytes(response.content)
    return download_file
