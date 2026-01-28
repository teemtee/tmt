"""
Pidfile handling.

tmt must make sure running a script must allow for multiple external
factors: the test timeout, interactivity, reboots and ``tmt-reboot``
invocations. tmt must present consistent info on what is the PID to
kill from ``tmt-reboot``, and where to save additional reboot info.

.. note::

    Historically, this is mostly visible with tests, but the concept
    applies to all restartable actions on the guest: ``prepare/shell``
    scripts, ``finish/ansible`` playbooks, and so on.

To achieve these goals, tmt uses two wrappers, the inner and the outer
one. The inner one wraps the actual action: a test script as defined
in test metadata, ``prepare/shell`` script, or ``ansible-playbook``
invocation. The outer one then runs the inner wrapper while
performing the necessary setup and accounting. The inner wrapper is
driven by user-provided inputs, while the outer contains what tmt itself
needs to do to correctly integrate the action with tmt. tmt invokes the
outer wrapper which then invokes the inner wrapper which then invokes
the action.

The inner wrapper exists to give tmt a single command to run to invoke
the action. Test or ``prepare`` script may be a single command, but also
a multiline, complicated shell script. To avoid issues with quotes and
escaping things here and there, tmt saves the action into the inner
wrapper, and then the outer wrapper can work with just a single
executable shell script.

For the duration of the action, the outer wrapper creates so-called
"pidfile". The pidfile contains outer wrapper PID and path to the
reboot-request file corresponding to the action being run. All actions
against the pidfile must be taken while holding the pidfile lock,
to serialize access between the wrapper and ``tmt-reboot``. The file
might be missing, that's allowed, but if it exists, it must contain
correct info.

Before quitting the outer wrapper, the pidfile is removed. There seems
to be an apparent race condition: action quits -> ``tmt-reboot`` is
called from a parallel session, grabs a pidfile lock, inspects
pidfile, updates reboot-request, and sends signal to designed PID
-> wrapper grabs the lock & removes the pidfile. This leaves us
with ``tmt-reboot`` sending signal to non-existent PID - which is
reported by ``tmt-reboot``, "try again later" - and reboot-request
file signaling reboot is needed *after the action is done*.

This cannot be solved without the action being involved in the reboot,
which does not seem like a viable option. The actions must be restartable
though, it may get restarted in this "weird" way. On the other hand,
this is probably not a problem in real-life scenarios: actions that
are to be interrupted by out-of-session reboot are expecting this
event, and they do not finish on their own.

The ssh client always allocates a tty, so the timeout handling works
(#1387). Because the allocated tty is generally not suitable for the
execution of test, or scripts in general, the wrapper uses ``|& cat`` to
emulate execution without a tty. In certain cases, where the execution
of given action with available tty is required (#2381), the tty can be
enabled in the outer script.

The outer wrapper handles the following 3 execution modes:

* In the interactive mode, stdin and stdout are unhandled, it is expected
  user interacts with the executed command.
* In the non-interactive mode without a tty, stdin is fed with
  ``/dev/null`` (EOF), and ``|& cat`` is used to simulate the "no tty
  available" for the running action.
* In the non-interactive mode with a tty, stdin is available to the
  action, and the simulation of "tty not available" for output is not
  run.
"""

import functools
import os
from typing import Any, Optional

import jinja2

import tmt.log
import tmt.steps
from tmt.container import container
from tmt.steps import safe_filename
from tmt.steps.provision import Guest, TransferOptions
from tmt.utils import Environment, EnvVarValue, HasEnvironment, Path, ShellScript
from tmt.utils.templates import render_template

TEST_PIDFILE_FILENAME = 'tmt-test.pid'
TEST_PIDFILE_LOCK_FILENAME = f'{TEST_PIDFILE_FILENAME}.lock'

#: The default directory for storing test pid file.
TEST_PIDFILE_ROOT = Path('/var/tmp')  # noqa: S108 insecure usage of temporary dir

#: A template for the inner wrapper which invokes the action script.
INNER_WRAPPER_TEMPLATE = jinja2.Template("""
{{ ACTION }}
""")

#: A template for the outer wrapper which handles most of the
#: orchestration and invokes the inner wrapper.
OUTER_WRAPPER_TEMPLATE = jinja2.Template("""
{% macro log_to_dmesg(msg) %}
    {%- if not GUEST.facts.is_superuser %}
        {%- if GUEST.become %}
# Logging test into kernel log
sudo bash -c "echo \\\"{{ msg }}\\\" > /dev/kmsg"
        {%- else %}
# Not logging into kernel log: not a superuser, 'become' not enabled
# echo \"{{ msg }}\" > /dev/kmsg
        {%- endif %}
    {%- else %}
# Logging test into kernel log
echo "{{ msg }}" > /dev/kmsg
    {%- endif %}
{% endmacro %}

{% macro enter() %}
# Updating the tmt test pid file
mkdir -p "$(dirname $TMT_TEST_PIDFILE_LOCK)"
flock "$TMT_TEST_PIDFILE_LOCK" -c "echo '${test_pid} ${TMT_REBOOT_REQUEST}' > ${TMT_TEST_PIDFILE}" || exit 122

{% if BEFORE_MESSAGE %}
{{
    log_to_dmesg(BEFORE_MESSAGE)
}}
{% endif %}
{%- endmacro %}

{% macro exit() %}
{% if AFTER_MESSAGE %}
{{
    log_to_dmesg(AFTER_MESSAGE)
}}
{% endif %}

# Updating the tmt test pid file
mkdir -p "$(dirname $TMT_TEST_PIDFILE_LOCK)"
flock "$TMT_TEST_PIDFILE_LOCK" -c "rm -f ${TMT_TEST_PIDFILE}" || exit 123
{%- endmacro %}

# Make sure guest scripts path is searched by shell
if ! grep -q "{{ GUEST.scripts_path }}" <<< "${PATH}"; then
    export PATH={{ GUEST.scripts_path }}:${PATH}
fi

[ ! -z "$TMT_DEBUG" ] && set -x

test_pid="$$"

{% if WITH_INTERACTIVE %}
{{ enter() }}

{{ COMMAND }}
_exit_code="$?"

{{ exit() }}

{% elif WITH_TTY %}
set -o pipefail

{{ enter() }}

{{ COMMAND }} 2>&1
_exit_code="$?"

{{ exit () }}

{% else %}
set -o pipefail

{{ enter() }}

{{ COMMAND }} </dev/null |& cat
_exit_code="$?"

{{ exit () }}
{% endif %}

# Return the original exit code of the test script
exit $_exit_code
""")  # noqa: E501


def effective_pidfile_root() -> Path:
    """
    Find out what the actual pidfile directory is.

    If ``TMT_TEST_PIDFILE_ROOT`` variable is set, it is used. Otherwise,
    :py:const:`TEST_PIDFILE_ROOT` is picked.
    """

    if 'TMT_TEST_PIDFILE_ROOT' in os.environ:
        return Path(os.environ['TMT_TEST_PIDFILE_ROOT'])

    return TEST_PIDFILE_ROOT


@container
class PidFileContext(HasEnvironment):
    #: Phase owning this context.
    phase: tmt.steps.BasePlugin[Any, Any]

    #: Guest on which the action runs.
    guest: Guest

    #: Used for logging.
    logger: tmt.log.Logger

    @functools.cached_property
    def pidfile_path(self) -> Path:
        """
        Path to the pidfile.
        """

        return effective_pidfile_root() / TEST_PIDFILE_FILENAME

    @functools.cached_property
    def pidfile_lock_path(self) -> Path:
        """
        Path to the pidfile lock.
        """

        return effective_pidfile_root() / TEST_PIDFILE_LOCK_FILENAME

    @property
    def environment(self) -> Environment:
        return Environment(
            {
                'TMT_TEST_PIDFILE': EnvVarValue(self.pidfile_path),
                'TMT_TEST_PIDFILE_LOCK': EnvVarValue(self.pidfile_lock_path),
            }
        )

    def _create_wrapper(
        self,
        label: str,
        path: Path,
        filename_template: str,
        template: jinja2.Template,
        **variables: Any,
    ) -> Path:
        # tmt wrapper filenames *must* be "unique" - the plugin might be handling
        # the same `discover` phase for different guests at the same time, and
        # must keep them isolated. The wrapper scripts, while being prepared, are
        # a shared global state, and we must prevent race conditions.
        wrapper_filename = safe_filename(filename_template, self.phase, self.guest, **variables)

        wrapper_filepath = path / wrapper_filename
        self.logger.debug(f'{label} wrapper', wrapper_filepath)

        wrapper = ShellScript(template.render(GUEST=self.guest, **variables).strip())
        self.logger.debug(f'{label} wrapper', wrapper, level=3)

        self.phase.write(wrapper_filepath, str(wrapper), mode='w', permissions=0o755)
        self.guest.push(
            source=wrapper_filepath,
            destination=wrapper_filepath,
            options=TransferOptions(protect_args=True, preserve_perms=True, chmod=0o755),
        )

        return wrapper_filepath

    def create_wrappers(
        self,
        path: Path,
        inner_filename_template: str,
        outer_filename_template: str,
        before_message_template: Optional[str] = None,
        after_message_template: Optional[str] = None,
        **variables: Any,
    ) -> tuple[Path, Path]:
        inner_wrapper_filepath = self._create_wrapper(
            'inner', path, inner_filename_template, INNER_WRAPPER_TEMPLATE, **variables
        )

        outer_wrapper_filepath = self._create_wrapper(
            'outer',
            path,
            outer_filename_template,
            OUTER_WRAPPER_TEMPLATE,
            COMMAND=ShellScript(f'./{inner_wrapper_filepath.name}'),
            BEFORE_MESSAGE=render_template(before_message_template, **variables)
            if before_message_template
            else None,
            AFTER_MESSAGE=render_template(after_message_template, **variables)
            if after_message_template
            else None,
            **variables,
        )

        return (inner_wrapper_filepath, outer_wrapper_filepath)
