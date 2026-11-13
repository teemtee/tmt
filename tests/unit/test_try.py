from types import SimpleNamespace
from typing import Any

import click
import pytest

import tmt.cli.trying
import tmt.steps.prepare
import tmt.steps.provision
import tmt.utils


@pytest.mark.parametrize(
    ('params', 'expected'),
    [
        (
            {'image_and_how': ('fedora@virtual',), 'arch': None, 'flavor': None},
            {'image': 'fedora', 'how': 'virtual'},
        ),
        (
            {'image_and_how': ('fedora@virtual',), 'arch': 'aarch64', 'flavor': None},
            {'image': 'fedora', 'how': 'virtual', 'arch': 'aarch64'},
        ),
        (
            {'image_and_how': ('@local',), 'arch': None, 'flavor': None},
            {'how': 'local'},
        ),
        (
            {'image_and_how': (), 'arch': 'aarch64', 'flavor': None},
            {'arch': 'aarch64'},
        ),
        (
            {'image_and_how': ('fedora@minute',), 'arch': None, 'flavor': 'u1.large'},
            {'image': 'fedora', 'how': 'minute', 'flavor': 'u1.large'},
        ),
        (
            {'image_and_how': ('fedora@minute',), 'arch': 'aarch64', 'flavor': 'u1.small'},
            {'image': 'fedora', 'how': 'minute', 'arch': 'aarch64', 'flavor': 'u1.small'},
        ),
        (
            {'image_and_how': ('fedora@virtual',), 'arch': None, 'flavor': 'u1.large'},
            {'image': 'fedora', 'how': 'virtual', 'flavor': 'u1.large'},
        ),
        (
            {'image_and_how': (), 'arch': None, 'flavor': 'u1.nano'},
            {'flavor': 'u1.nano'},
        ),
    ],
)
def test_options_arch_and_flavor(params: dict[str, Any], expected: dict[str, Any]):
    assert tmt.cli.trying._construct_trying_provision_options(params) == expected


@pytest.mark.parametrize(
    ('args', 'expected'),
    [
        # No step options
        (['fedora@minute'], (['fedora@minute'], None)),
        (['fedora@local'], (['fedora@local'], None)),
        ([], ([], None)),
        # Step options are split on the first step name
        (
            ['fedora@minute', 'provision', '--flavor', 'u1.large'],
            (['fedora@minute'], ['provision', '--flavor', 'u1.large']),
        ),
        (
            ['fedora@local', 'prepare', '--insert', '--how', 'install', '--package', 'tree'],
            (['fedora@local'], ['prepare', '--insert', '--how', 'install', '--package', 'tree']),
        ),
        # The first step wins
        (
            ['fedora@local', 'prepare', '--insert', 'provision', '--how', 'container'],
            (['fedora@local'], ['prepare', '--insert', 'provision', '--how', 'container']),
        ),
        # A step name consumed as an option value must not trigger the split
        (
            ['-t', 'provision', 'fedora@local'],
            (['-t', 'provision', 'fedora@local'], None),
        ),
        (
            ['--test', 'prepare', 'fedora@local'],
            (['--test', 'prepare', 'fedora@local'], None),
        ),
        # The `--option=value` syntax does not consume the next argument
        (['--test=provision', 'fedora@local'], (['--test=provision', 'fedora@local'], None)),
        # Try options given after the image are kept
        (
            ['fedora@local', '-p', '/plans/basic', 'prepare', '--how', 'shell'],
            (['fedora@local', '-p', '/plans/basic'], ['prepare', '--how', 'shell']),
        ),
        # A step name after the `--` separator is a positional argument
        (['--', 'provision'], (['--', 'provision'], None)),
        # Abbreviated step names are resolved to the full name
        (
            ['fedora@minute', 'prov', '--flavor', 'u1.large'],
            (['fedora@minute'], ['provision', '--flavor', 'u1.large']),
        ),
        (
            ['fedora@local', 'prep', '--how', 'shell'],
            (['fedora@local'], ['prepare', '--how', 'shell']),
        ),
        # Ambiguous abbreviations are not treated as step names
        (['fedora@local', 'p', 'x'], (['fedora@local', 'p', 'x'], None)),
    ],
)
def test_split_step_arguments(args: list[str], expected: tuple[list[str], Any]):
    assert tmt.cli.trying.split_step_arguments(args, tmt.cli.trying.try_command) == expected


def make_try_context(image_and_how: tuple[str, ...]) -> click.Context:
    """
    Prepare a click context resembling the one of `tmt try`
    """

    context = click.Context(tmt.cli.trying.try_command, info_name='try')
    context.params = {'image_and_how': image_and_how}
    context.obj = SimpleNamespace(steps=set(), run=None)

    return context


@pytest.fixture(name='reset_cli_invocations')
def fixture_reset_cli_invocations() -> Any:
    """
    Reset the class-level CLI invocation storage before and after a test
    """

    step_classes = (tmt.steps.provision.Provision, tmt.steps.prepare.Prepare)

    for klass in step_classes:
        klass.cli_invocation = None

    yield

    for klass in step_classes:
        klass.cli_invocation = None


@pytest.mark.usefixtures('reset_cli_invocations')
@pytest.mark.parametrize(
    ('image_and_how', 'step_arguments', 'expected'),
    [
        # The `--how` option is injected from the `image@method` syntax
        (
            ('fedora@container',),
            ['provision', '--image', 'quay.io/fedora/rawhide'],
            {'how': 'container', 'image': 'quay.io/fedora/rawhide'},
        ),
        # An explicit `--how` option is respected and not duplicated
        (
            ('fedora@container',),
            ['provision', '--how', 'container', '--image', 'quay.io/fedora/rawhide'],
            {'how': 'container', 'image': 'quay.io/fedora/rawhide'},
        ),
        # Options of other steps are applied as well
        (
            ('fedora@local',),
            ['prepare', '--insert', '--how', 'shell', '--script', 'true'],
            {'how': 'shell'},
        ),
    ],
)
def test_apply_step_arguments(
    image_and_how: tuple[str, ...], step_arguments: list[str], expected: dict[str, Any]
) -> None:
    tmt.cli.trying.stash_step_arguments(step_arguments)
    tmt.cli.trying._apply_step_arguments(make_try_context(image_and_how))

    invocations = [
        tmt.steps.provision.Provision.cli_invocation,
        tmt.steps.prepare.Prepare.cli_invocation,
    ]
    invocation = next(invocation for invocation in invocations if invocation is not None)

    for key, value in expected.items():
        assert invocation.options[key] == value
        assert invocation.option_sources[key] == click.core.ParameterSource.COMMANDLINE


@pytest.mark.usefixtures('reset_cli_invocations')
def test_apply_step_arguments_unsupported_method() -> None:
    tmt.cli.trying.stash_step_arguments(['provision', '--how', 'bogus'])

    with pytest.raises(tmt.utils.GeneralError, match='unsupported method'):
        tmt.cli.trying._apply_step_arguments(make_try_context(('fedora@container',)))


@pytest.mark.usefixtures('reset_cli_invocations')
def test_apply_step_arguments_invalid_subcommand() -> None:
    tmt.cli.trying.stash_step_arguments(['prepare', 'bogus-argument'])

    with pytest.raises(tmt.utils.GeneralError, match='Invalid subcommand'):
        tmt.cli.trying._apply_step_arguments(make_try_context(('fedora@container',)))


@pytest.mark.usefixtures('reset_cli_invocations')
def test_apply_step_arguments_unknown_option() -> None:
    tmt.cli.trying.stash_step_arguments(['provision', '--bogus'])

    with pytest.raises(click.UsageError, match=r'[Nn]o such option'):
        tmt.cli.trying._apply_step_arguments(make_try_context(('fedora@container',)))
