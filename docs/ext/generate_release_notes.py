"""
Sphinx extension to generate ``releases/releases_inc.rst`` file
"""
# TODO: For now we manually generate the content until we have the
#  tmt:autostory to more natively integrate it.

import typing

if typing.TYPE_CHECKING:
    from sphinx.application import Sphinx


import tmt
from tmt._compat.pathlib import Path


def generate_release_notes(app: "Sphinx") -> None:
    """
    Generate ``releases/releases_inc.rst`` file
    """

    # We will need a logger...
    logger = tmt.Logger.create()
    logger.add_console_handler()
    tree = tmt.Tree(logger=logger, path=Path(app.confdir / "releases"))

    release_inc = app.confdir / "releases/release.rst.inc"
    with release_inc.open("w") as doc:
        # The release notes structure is /<release>/<issue|note>
        for release in tree.stories(names=[r"^/[\d\.]+$"], whole=True):
            title = f"tmt-{release.name.removeprefix('/')}"
            doc.write(f"{title}\n{'~' * len(title)}\n\n")
            # For now we just paste in the `description` content
            for release_note in tree.stories(names=[rf"^{release.name}/.*"]):
                doc.write(release_note.description)
                doc.write("\n")
            doc.write("\n")


def setup(app: "Sphinx"):
    app.connect("builder-inited", generate_release_notes)
