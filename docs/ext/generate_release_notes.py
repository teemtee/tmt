"""
Sphinx extension to generate ``releases/releases.rst.inc`` file
"""
# TODO: For now we manually generate the content until we have the
#  tmt:autostory to more natively integrate it.

import typing

if typing.TYPE_CHECKING:
    from sphinx.application import Sphinx


from packaging.version import Version

import tmt
from tmt._compat.pathlib import Path


def generate_release_notes(app: "Sphinx") -> None:
    """
    Generate ``releases/releases_inc.rst.inc`` file
    """

    # We will need a logger...
    logger = tmt.Logger.create()
    logger.add_console_handler()
    tree = tmt.Tree(logger=logger, path=Path(app.confdir / "releases"))

    release_inc = app.confdir / "releases/release.rst.inc"
    with release_inc.open("w") as doc:
        # The release notes structure is /<release>/<issue|note>
        for release in sorted(
            tree.stories(names=[r"^/(?:[\d\.]+|pending)$"], whole=True),
            key=lambda x: (
                Version('9999') if x.name == '/pending' else Version(x.name.removeprefix("/"))
            ),
            reverse=True,
        ):
            release_notes = tree.stories(names=[rf"^{release.name}/.*"])

            if release.name == '/pending':
                title = 'pending'
                intro = '\n.. note::\n\n    These are the release notes for the upcoming tmt release.\n\n'  # noqa: E501

            else:
                title = f"tmt-{release.name.removeprefix('/')}"
                intro = ''

            doc.write(f"{title}\n{'~' * len(title)}\n\n")
            doc.write(intro)
            # For now we just paste in the `description` content
            for release_note in release_notes:
                doc.write(release_note.description)
                doc.write("\n")
            doc.write("\n")


def setup(app: "Sphinx"):
    app.connect("builder-inited", generate_release_notes)
