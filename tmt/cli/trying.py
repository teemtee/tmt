""" ``tmt try`` implementation """

import re
from typing import Any

import click

import tmt.steps.provision
import tmt.trying
import tmt.utils
from tmt.cli import Context, pass_context
from tmt.cli._root import force_dry_options, main, verbosity_options
from tmt.options import option


@main.command(name="try")
@pass_context
@click.argument("image_and_how", nargs=-1, metavar="IMAGE[@HOW]")
@option(
    "-t", "--test", default=[], metavar="REGEXP", multiple=True,
    help="""
        Run tests matching given regular expression.
        By default all tests under the current working directory are executed.
        """)
@option(
    "-p", "--plan", default=[], metavar="REGEXP", multiple=True,
    help="""
        Use provided plan. By default user config is checked for plans
        named as '/user/plan*', default plan is used otherwise.
        """)
@option(
    "-l", "--login", is_flag=True, default=False,
    help="Log into the guest only, do not run any tests.")
@option(
    "--epel", is_flag=True, default=False,
    help="Enable epel repository.")
@option(
    "--install", default=[], metavar="PACKAGE", multiple=True,
    help="Install package on the guest.")
@option(
    "--arch", default=None, metavar="ARCH", multiple=False,
    help="Specify guest CPU architecture.")
@option(
    "-a", "--ask", is_flag=True, default=False,
    help="Just provision the guest and ask what to do next.")
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
    """

    tmt.trying.Try.store_cli_invocation(context)

    # Inject custom image and provision method to the Provision options
    options = _construct_trying_provision_options(context.params)
    if options:
        tmt.steps.provision.Provision.store_cli_invocation(
            context=None, options=options)

    # Finally, let's start trying!
    trying = tmt.trying.Try(
        tree=context.obj.tree,
        logger=context.obj.logger)

    trying.go()


def _construct_trying_provision_options(params: Any) -> dict[str, Any]:
    """ Convert try-specific options into generic option format """
    options: dict[str, Any] = {}

    if params['image_and_how']:
        # TODO: For now just pick the first image-how pair, let's allow
        # specifying multiple images and provision methods as well
        image_and_how = params['image_and_how'][0]
        # We expect the 'image' or 'image@how' syntax
        matched = re.match("([^@]+)@([^@]+)", image_and_how.strip())
        if matched:
            options = {"image": matched.group(1), "how": matched.group(2)}
        else:
            options = {"image": image_and_how}

    # Add guest architecture if provided
    if params['arch']:
        options['arch'] = params['arch']

    # For 'connect' rename 'image' to 'guest'
    if options.get('how') == 'connect':
        options['guest'] = options.pop('image')

    return options
