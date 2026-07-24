"""
Url handling helpers.
"""

import email.message

import tmt.log
import tmt.utils
from tmt.utils import Path


def download(url: str, destination: Path, *, logger: tmt.log.Logger) -> Path:
    logger.debug(f"Downloading '{url}'.")
    with tmt.utils.retry_session(logger=logger) as session:
        response = session.get(url, stream=True)
    response.raise_for_status()
    if destination.is_dir():
        file_name = None
        if "Content-Disposition" in response.headers:
            # We use email.message to parse the Content-Disposition header since the regex can get
            # quite complicate. We do not support `filename*` with this yet, but that is even more
            # complicated to handle. Waiting on a better library to handle it.
            # See: https://stackoverflow.com/a/12017573
            _msg_handler = email.message.Message()
            _msg_handler["Content-Disposition"] = response.headers["Content-Disposition"]
            # If this one fails, it should return a None object, then try to get from url instead
            file_name = _msg_handler.get_filename()
        if not file_name:
            file_name = response.url.split("/")[-1]
    else:
        if destination.exists():
            raise tmt.utils.GeneralError(f"Destination file already exists: {destination}")
        file_name = destination.name
        destination = destination.parent
    assert isinstance(file_name, str)  # Narrow type
    download_file = destination / file_name
    with download_file.open(mode="wb") as f:
        for chunk in response.iter_content(chunk_size=None):
            f.write(chunk)
    return download_file
