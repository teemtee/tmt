"""
``tmt try`` implementation
"""

import re
from typing import Any, Optional

import click

import tmt.steps
import tmt.steps.provision
import tmt.trying
from tmt.cli import Context, pass_context
from tmt.cli._root import environment_options, force_dry_options, main, verbosity_options
from tmt.options import option  # pyright: ignore[reportUnknownVariableType]
from tmt.utils import GeneralError, SpecificationError


@main.command(name="try")
@pass_context
@click.argument("image_and_how", nargs=-1, metavar="IMAGE[@HOW]")
@option(
    "-t",
    "--test",
    default=[],
    metavar="REGEXP",
    multiple=True,
    help="""
        Run tests matching given regular expression.
        By default all tests under the current working directory are executed.
        """,
)
@option(
    "-p",
    "--plan",
    default=[],
    metavar="REGEXP",
    multiple=True,
    help="""
        Use provided plan. By default user config is checked for plans
        named as '/user/plan*', default plan is used otherwise.
        """,
)
@option(
    "-l",
    "--login",
    is_flag=True,
    default=False,
    help="Log into the guest only, do not run any tests.",
)
@option(
    "--epel",
    is_flag=True,
    default=False,
    help="Enable epel repository.",
)
@option(
    "--fips",
    is_flag=True,
    default=False,
    help="Enable FIPS mode.",
)
@option(
    "--install",
    default=[],
    metavar="PACKAGE",
    multiple=True,
    help="Install package on the guest.",
)
@option(
    "--arch",
    default=None,
    metavar="ARCH",
    multiple=False,
    help="Specify guest CPU architecture.",
)
@option(
    "--flavor",
    default=None,
    metavar="FLAVOR",
    multiple=False,
    help="""
        Specify the hardware flavor for the guest.
        Supported by provision plugins such as minute, use
        'tmt run provision --how minute --list-flavors'
        to see what's available.
        """,
)
@option(
    "-a",
    "--ask",
    is_flag=True,
    default=False,
    help="Just provision the guest and ask what to do next.",
)
@environment_options
@verbosity_options
@force_dry_options
def try_command(context: Context, **kwargs: Any) -> None:
    """
    Try tests or experiment with guests.

    Provide an interactive session to run tests or play with guests.
    Provisions a guest, runs tests from the current working directory
    and provides menu with available options what to do next. If no
    tests are detected logs into the guest to start experimenting.

    In order to specify the guest just use the desired image name:

        tmt try fedora

    It's also possible to select the provision method for each guest:

    \b
        tmt try fedora@container
        tmt try centos-stream-9@virtual

    Or connect to the running guest by specifying FQDN or IP address:

    \b
        tmt try 192.168.12.23@connect

    It's also possible to provide options for individual steps, they are
    applied in the same way as when running `tmt run`:

    \b
        tmt try fedora@minute provision --flavor u1.large
        tmt try fedora@local prepare --insert --how install --package tree
    """

    tmt.trying.Try.store_cli_invocation(context)

    # Inject custom image and provision method to the Provision options
    options = _construct_trying_provision_options(context.params)
    if options:
        tmt.steps.provision.Provision.store_cli_invocation(context=None, options=options)

    # Apply options for steps given after the image, e.g.
    # `tmt try fedora@minute provision --flavor u1.large`
    _apply_step_arguments(context)

    # Finally, let's start trying!
    trying = tmt.trying.Try(tree=context.obj.tree, logger=context.obj.logger)

    trying.go()


def _construct_trying_provision_options(params: Any) -> dict[str, Any]:
    """
    Convert try-specific options into generic option format
    """

    options: dict[str, Any] = {}

    if params['image_and_how']:
        # TODO: For now just pick the first image-how pair, let's allow
        # specifying multiple images and provision methods as well
        image_and_how = params['image_and_how'][0].strip()
        # Handle local provisioning - image part is irrelevant
        if image_and_how == '@local':
            options = {"how": image_and_how[1:]}
        else:
            # We expect the 'image' or 'image@how' syntax
            matched = re.match("([^@]+)@([^@]+)", image_and_how)
            if matched:
                options = {"image": matched.group(1), "how": matched.group(2)}
            else:
                options = {"image": image_and_how}

    # Add guest architecture if provided
    if params['arch']:
        options['arch'] = params['arch']

    # Add guest flavor if provided
    if params['flavor']:
        options['flavor'] = params['flavor']

    # For 'connect' rename 'image' to 'guest'
    if options.get('how') == 'connect':
        options['guest'] = options.pop('image')

    return options


# Step options detected on the `tmt try` command line, e.g.
# `tmt try fedora@minute provision --flavor u1.large`
_pending_step_arguments: Optional[list[str]] = None


def _options_consuming_value(command: click.Command) -> set[str]:
    """
    Find options which consume a value on the command line
    """

    value_options: set[str] = set()

    for param in command.params:
        if not isinstance(param, click.Option):
            continue

        # Flags and countable options do not consume a separate value
        if param.is_flag or param.count:
            continue

        value_options.update(param.opts)
        value_options.update(param.secondary_opts)

    return value_options


def _resolve_step_name(arg: str) -> Optional[str]:
    """
    Resolve a step name given on the ``tmt try`` command line

    Accept both the full step name and its unique prefix, e.g. ``prov``
    or ``provision``, mirroring the command shortening of ``tmt run``.
    """

    if arg in tmt.steps.STEPS:
        return arg

    matches = [step for step in tmt.steps.STEPS if step.startswith(arg)]

    if len(matches) == 1:
        return matches[0]

    return None


def split_step_arguments(
    args: list[str], command: click.Command
) -> tuple[list[str], Optional[list[str]]]:
    """
    Split step options from the ``tmt try`` command line

    Detect the first step name (or its unique prefix, e.g. ``prov``)
    which is not consumed by an option, and split the command line there.
    Returns the arguments belonging to the ``tmt try`` command itself and
    the detected step arguments (``None`` if there are none).
    """

    value_options = _options_consuming_value(command)

    index = 0
    while index < len(args):
        arg = args[index]

        # Everything after the `--` separator is a positional argument
        if arg == '--':
            break

        step_name = _resolve_step_name(arg)
        if step_name is not None:
            return args[:index], [step_name, *args[index + 1 :]]

        if arg.startswith('--'):
            # `--option=value` does not consume the next argument
            if '=' not in arg and arg in value_options:
                index += 1

        elif arg.startswith('-') and arg in value_options:
            index += 1

        index += 1

    return args, None


def stash_step_arguments(step_arguments: Optional[list[str]]) -> None:
    """
    Save step options for later use by the ``tmt try`` command
    """

    global _pending_step_arguments
    _pending_step_arguments = step_arguments


def _apply_step_arguments(context: Context) -> None:
    """
    Apply step options given on the ``tmt try`` command line

    Invoke the corresponding step command with the collected options so
    that they are stored and applied to the plan in the same way as when
    running `tmt run`.
    """

    global _pending_step_arguments

    if _pending_step_arguments is None:
        return

    step_arguments = _pending_step_arguments
    _pending_step_arguments = None

    step_name, step_options = step_arguments[0], step_arguments[1:]

    import tmt.steps.cleanup
    import tmt.steps.discover
    import tmt.steps.execute
    import tmt.steps.finish
    import tmt.steps.prepare
    import tmt.steps.provision
    import tmt.steps.report

    plugin_classes: dict[str, Any] = {
        'discover': tmt.steps.discover.DiscoverPlugin,
        'provision': tmt.steps.provision.ProvisionPlugin,
        'prepare': tmt.steps.prepare.PreparePlugin,
        'execute': tmt.steps.execute.ExecutePlugin,
        'report': tmt.steps.report.ReportPlugin,
        'finish': tmt.steps.finish.FinishPlugin,
        'cleanup': tmt.steps.cleanup.CleanupPlugin,
    }
    command = plugin_classes[step_name].command()

    # The provision method might be provided by the `image@method` syntax.
    # Inject it as `--how` so that method-specific options are accepted
    # as well, e.g. `--flavor` of the `minute` plugin.
    if (
        step_name == 'provision'
        and context.params['image_and_how']
        and not any(
            option in ('-h', '--how') or option.startswith('--how=') for option in step_options
        )
    ):
        image_and_how = context.params['image_and_how'][0].strip()
        matched = re.match('[^@]+@([^@]+)', image_and_how)
        if matched:
            step_options = ['--how', matched.group(1), *step_options]

    try:
        step_context = command.make_context(step_name, step_options, parent=context)
        command.invoke(step_context)

    except click.ClickException:
        # Let click report unknown options and similar issues
        raise

    except AssertionError as error:
        # `_check_method` requires a run to exist to report an
        # unsupported method, which is not the case with `tmt try`.
        # Provide a friendlier message instead of the empty error.
        raise GeneralError(
            f"Failed to apply '{step_name}' step options: unsupported method."
        ) from error

    except SpecificationError as error:
        raise GeneralError(f"Failed to apply '{step_name}' step options: {error}") from error
