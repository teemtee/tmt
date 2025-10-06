import os
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Callable, Optional

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.utils
import tmt.utils.signals
import tmt.utils.wait
from tmt.container import container
from tmt.utils import (
    Path,
)
from tmt.utils.templates import render_template_file

if TYPE_CHECKING:
    import tmt.steps.provision

#: Scripts source directory
SCRIPTS_SRC_DIR = tmt.utils.resource_files('steps/scripts')

#: The default scripts destination directory
DEFAULT_SCRIPTS_DEST_DIR = Path("/usr/local/bin")

#: The default scripts destination directory for rpm-ostree based distributions, https://github.com/teemtee/tmt/discussions/3260
DEFAULT_SCRIPTS_DEST_DIR_OSTREE = Path("/var/lib/tmt/scripts")

#: The tmt environment variable name for forcing ``SCRIPTS_DEST_DIR``
SCRIPTS_DEST_DIR_VARIABLE = 'TMT_SCRIPTS_DIR'

#: The directory where helper scripts will be copied
SCRIPTS_DIR_NAME = "scripts"


@container
class Script:
    """
    Represents a script provided by the internal executor.

    Must be used as a context manager. The context manager returns
    the source filename.

    The source file is defined by the ``source_filename`` attribute and its
    location is relative to the directory specified via the :py:data:`SCRIPTS_SRC_DIR`
    variable. All scripts must be located in this directory.

    The default destination directory of the scripts is :py:data:`DEFAULT_SCRIPTS_DEST_DIR`.
    On ``rpm-ostree`` distributions like Fedora CoreOS, the default destination
    directory is :py:data:``DEFAULT_SCRIPTS_DEST_DIR_OSTREE``. The destination directory
    of the scripts can be forced by the script using ``destination_path`` attribute.

    The destination directory can be overridden using the environment variable defined
    by the :py:data:`DEFAULT_SCRIPTS_DEST_DIR_VARIABLE` variable.

    The ``enabled`` attribute can specify a function which is called with :py:class:`Guest`
    instance to evaluate if the script is enabled. This can be useful to optionally disable
    a script for specific guests.
    """

    source_filename: str
    destination_path: Optional[Path]
    aliases: list[str]
    related_variables: list[str]
    enabled: Callable[['tmt.steps.provision.Guest'], bool]

    def __enter__(self) -> Path:
        return SCRIPTS_SRC_DIR / self.source_filename

    def __exit__(self, *args: object) -> None:
        pass


@container
class ScriptCreatingFile(Script):
    """
    Represents a script which creates a file.

    See :py:class:`Script` for more details.
    """

    created_file: str


@container
class ScriptTemplate(Script):
    """
    Represents a Jinja2 templated script.

    The source filename is constructed from the name of the file specified
    via the ``source_filename`` attribute, with the ``.j2`` suffix appended.
    The template file must be located in the directory specified
    via :py:data:`SCRIPTS_SRC_DIR` variable.
    """

    context: dict[str, str]

    _rendered_script_path: Optional[Path] = None

    def __enter__(self) -> Path:
        with NamedTemporaryFile(mode='w', delete=False) as rendered_script:
            rendered_script.write(
                render_template_file(
                    SCRIPTS_SRC_DIR / f"{self.source_filename}.j2", None, **self.context
                )
            )

        self._rendered_script_path = Path(rendered_script.name)

        return self._rendered_script_path

    def __exit__(self, *args: object) -> None:
        assert self._rendered_script_path
        os.unlink(self._rendered_script_path)


def effective_scripts_dest_dir(default: Path = DEFAULT_SCRIPTS_DEST_DIR) -> Path:
    """
    Find out what the actual scripts destination directory is.

    If the ``TMT_SCRIPTS_DIR`` environment variable is set, it is used
    as the scripts destination directory. Otherwise, the ``default``
    parameter path is returned.
    """

    return Path(os.environ.get(SCRIPTS_DEST_DIR_VARIABLE, default))


# Script handling reboots, in restraint compatible fashion
TMT_REBOOT_SCRIPT = ScriptCreatingFile(
    source_filename='tmt-reboot',
    destination_path=None,
    aliases=[
        'rstrnt-reboot',
        'rhts-reboot',
    ],
    related_variables=[
        "TMT_REBOOT_COUNT",
        "REBOOTCOUNT",
        "RSTRNT_REBOOTCOUNT",
    ],
    created_file="reboot-request",
    enabled=lambda _: True,
)

TMT_REBOOT_CORE_SCRIPT = Script(
    source_filename='tmt-reboot-core',
    destination_path=None,
    aliases=[],
    related_variables=[],
    enabled=lambda _: True,
)

# Script handling result reporting, in restraint compatible fashion
TMT_REPORT_RESULT_SCRIPT = ScriptCreatingFile(
    source_filename='tmt-report-result',
    destination_path=None,
    aliases=[
        'rstrnt-report-result',
        'rhts-report-result',
    ],
    related_variables=[],
    created_file="tmt-report-results.yaml",
    enabled=lambda _: True,
)

# Script for archiving a file, usable for BEAKERLIB_COMMAND_SUBMIT_LOG
TMT_FILE_SUBMIT_SCRIPT = Script(
    source_filename='tmt-file-submit',
    destination_path=None,
    aliases=[
        'rstrnt-report-log',
        'rhts-submit-log',
        'rhts_submit_log',
    ],
    related_variables=[],
    enabled=lambda _: True,
)

# Script handling text execution abortion, in restraint compatible fashion
TMT_ABORT_SCRIPT = ScriptCreatingFile(
    source_filename='tmt-abort',
    destination_path=None,
    aliases=[
        'rstrnt-abort',
        'rhts-abort',
    ],
    related_variables=[],
    created_file="abort",
    enabled=lambda _: True,
)

# Profile script for adding SCRIPTS_DEST_DIR to executable paths system-wide.
# Used only for distributions using rpm-ostree.
TMT_ETC_PROFILE_D = ScriptTemplate(
    source_filename='tmt.sh',
    destination_path=Path("/etc/profile.d/tmt.sh"),
    aliases=[],
    related_variables=[],
    context={
        'SCRIPTS_DEST_DIR': str(
            effective_scripts_dest_dir(default=DEFAULT_SCRIPTS_DEST_DIR_OSTREE)
        )
    },
    # ignore[has-type]: mypy seems to not understand annotations here.
    enabled=lambda guest: guest.facts.is_ostree is True,
)


# List of all available scripts
SCRIPTS = (
    TMT_ABORT_SCRIPT,
    TMT_ETC_PROFILE_D,
    TMT_FILE_SUBMIT_SCRIPT,
    TMT_REBOOT_SCRIPT,
    TMT_REBOOT_CORE_SCRIPT,
    TMT_REPORT_RESULT_SCRIPT,
)
