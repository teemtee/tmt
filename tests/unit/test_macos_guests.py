"""
Tests for macOS guest support: guest facts, transfer options, Homebrew and the test wrapper.
"""

from typing import Optional, Union
from unittest.mock import MagicMock

import _pytest.monkeypatch
import pytest

import tmt.steps
from tmt.guest import (
    DEFAULT_PULL_OPTIONS,
    DEFAULT_PUSH_OPTIONS,
    GuestFacts,
    GuestSsh,
    GuestSshData,
    TransferOptions,
)
from tmt.log import Logger
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackageUrl,
    PrepareError,
)
from tmt.package_managers.apk import Apk
from tmt.package_managers.apt import Apt
from tmt.package_managers.homebrew import HOMEBREW_PREFIXES, Homebrew, HomebrewEngine
from tmt.steps.context.pidfile import OUTER_WRAPPER_TEMPLATE
from tmt.steps.execute.internal import ExecuteInternal
from tmt.steps.provision import Provision
from tmt.utils import (
    Command,
    CommandOutput,
    GeneralError,
    Path,
    RunError,
    ShellScript,
    effective_workdir_root,
)
from tmt.utils.environment import Environment, EnvVarValue

OPENRSYNC_VERSION = 'openrsync: protocol version 29\nrsync version 2.6.9 compatible\n'
RSYNC_VERSION = 'rsync  version 3.4.1  protocol version 32\n'

BREW = 'env PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin HOMEBREW_NO_AUTO_UPDATE=1 brew'  # noqa: E501

HOMEBREW_PREFIXES_PATH = ':'.join(HOMEBREW_PREFIXES)

# Commands run by guest facts, as they appear in `execute()` calls.
UNAME_S = str(Command('uname', '-s'))
RSYNC_VERSION_COMMAND = str(Command('rsync', '--version'))
SW_VERS = str(
    ShellScript('echo "$(sw_vers -productName) $(sw_vers -productVersion)"').to_shell_command()
)
SW_VERS_PRODUCT_VERSION = str(Command('sw_vers', '-productVersion'))
OS_RELEASE = str(Command('cat', '/etc/os-release'))


def _guest(outputs: dict[str, str]) -> MagicMock:
    """
    Guest mock answering ``execute()`` from a mapping of commands to their stdout.

    Commands missing from the mapping fail.
    """

    guest = MagicMock()

    def execute(command: Command, **kwargs: object) -> CommandOutput:
        if str(command) in outputs:
            return CommandOutput(stdout=outputs[str(command)], stderr='')

        raise RunError('failed', command, 1)

    guest.execute.side_effect = execute

    return guest


def _executed(guest: MagicMock, command: str) -> int:
    """
    Count how many times the guest mock executed the given command.
    """

    return sum(1 for call in guest.execute.call_args_list if str(call.args[0]) == command)


def _ssh_guest(root_logger: Logger, *, become: bool = False, dry_run: bool = False) -> GuestSsh:
    step = Provision(
        plan=MagicMock(name='mock<plan>', is_dry_run=dry_run), raw_data=[{}], logger=root_logger
    )

    return GuestSsh(
        logger=root_logger,
        parent=step,
        name='foo',
        data=GuestSshData(primary_address='bar', become=become),
    )


def _homebrew_guest(*, is_superuser: bool = False) -> MagicMock:
    """
    Guest mock for Homebrew, logged in as a regular user unless told otherwise.
    """

    guest = MagicMock()
    guest.facts = GuestFacts(in_sync=True, is_superuser=is_superuser)

    return guest


@pytest.mark.parametrize(
    ('outputs', 'expected', 'executed_once'),
    [
        (
            {
                UNAME_S: 'Darwin\n',
                SW_VERS: 'macOS 15.7.7\n',
                RSYNC_VERSION_COMMAND: OPENRSYNC_VERSION,
            },
            {
                'is_darwin': True,
                'has_rsync': True,
                'has_openrsync': True,
                'distro': 'macOS 15.7.7',
                'distro_id': 'macos',
                'distro_major_version': 15,
            },
            [UNAME_S, RSYNC_VERSION_COMMAND, SW_VERS],
        ),
        (
            {
                OS_RELEASE: 'ID=fedora\nVERSION_ID=43\nPRETTY_NAME="Fedora Linux 43"\n',
                UNAME_S: 'Linux\n',
                RSYNC_VERSION_COMMAND: RSYNC_VERSION,
            },
            {
                'is_darwin': False,
                'has_rsync': True,
                'has_openrsync': False,
                'distro': 'Fedora Linux 43',
                'distro_id': 'fedora',
                'distro_major_version': 43,
            },
            [UNAME_S, RSYNC_VERSION_COMMAND],
        ),
        (
            {
                UNAME_S: 'Darwin\n',
                SW_VERS_PRODUCT_VERSION: '26.1\n',
                RSYNC_VERSION_COMMAND: OPENRSYNC_VERSION,
            },
            {
                'is_darwin': True,
                'distro': None,
                'distro_id': 'macos',
                'distro_major_version': 26,
            },
            [UNAME_S, RSYNC_VERSION_COMMAND, SW_VERS, SW_VERS_PRODUCT_VERSION],
        ),
    ],
    ids=['darwin', 'linux', 'darwin-without-distro'],
)
def test_facts_sync(
    outputs: dict[str, str], expected: dict[str, object], executed_once: list[str]
) -> None:
    guest = _guest(outputs)
    facts = GuestFacts()

    facts.sync(guest)

    assert {fact: getattr(facts, fact) for fact in expected} == expected
    assert {command: _executed(guest, command) for command in executed_once} == dict.fromkeys(
        executed_once, 1
    )


@pytest.mark.parametrize(
    ('has_openrsync', 'is_darwin', 'expected_synced'),
    [
        (True, True, []),
        (False, False, []),
        (None, True, ['has_openrsync']),
        (True, None, ['is_darwin']),
        (None, None, ['has_openrsync', 'is_darwin']),
    ],
    ids=['macos', 'linux', 'missing-openrsync', 'missing-darwin', 'missing-both'],
)
def test_transfer_options_sync_missing_facts(
    root_logger: Logger,
    monkeypatch: _pytest.monkeypatch.MonkeyPatch,
    has_openrsync: Optional[bool],
    is_darwin: Optional[bool],
    expected_synced: list[str],
) -> None:
    guest = _ssh_guest(root_logger)
    guest.facts = GuestFacts(in_sync=True, has_openrsync=has_openrsync, is_darwin=is_darwin)

    sync = MagicMock()
    monkeypatch.setattr(guest.facts, 'sync', sync)

    guest._transfer_options(DEFAULT_PUSH_OPTIONS)

    if expected_synced:
        sync.assert_called_once_with(guest, *expected_synced)
    else:
        sync.assert_not_called()


def test_facts_sync_single_darwin_fact() -> None:
    guest = _guest({UNAME_S: 'Darwin\n', SW_VERS_PRODUCT_VERSION: '15.7.7\n'})
    facts = GuestFacts()

    facts.sync(guest, 'distro_major_version')

    assert facts.distro_major_version == 15
    # Asked once, on behalf of the distro fact, since `is_darwin` itself was not synced.
    assert _executed(guest, UNAME_S) == 1
    assert facts.is_darwin is None


@pytest.mark.parametrize(
    ('options', 'facts', 'pushing', 'expected'),
    [
        (
            DEFAULT_PUSH_OPTIONS,
            GuestFacts(),
            True,
            ['-z', '--delete', '--links', '-s', '-r', '-R', '--safe-links'],
        ),
        (
            DEFAULT_PUSH_OPTIONS,
            GuestFacts(has_openrsync=False, is_darwin=False),
            True,
            ['-z', '--delete', '--links', '-s', '-r', '-R', '--safe-links'],
        ),
        (
            DEFAULT_PUSH_OPTIONS,
            GuestFacts(has_openrsync=True, is_darwin=True),
            True,
            ['-z', '--delete', '--links', '-r', '-R', '--safe-links', '--no-implied-dirs'],
        ),
        (
            TransferOptions(protect_args=True, preserve_perms=True, chmod=0o755),
            GuestFacts(has_openrsync=True, is_darwin=True),
            True,
            ['--chmod=755', '-p', '--no-implied-dirs'],
        ),
        (
            DEFAULT_PULL_OPTIONS,
            GuestFacts(),
            False,
            ['-z', '--links', '-s', '-r', '-R', '--safe-links'],
        ),
        (
            DEFAULT_PULL_OPTIONS,
            GuestFacts(has_openrsync=False, is_darwin=False),
            False,
            ['-z', '--links', '-s', '-r', '-R', '--safe-links'],
        ),
        (
            DEFAULT_PULL_OPTIONS,
            GuestFacts(has_openrsync=True, is_darwin=True),
            False,
            ['-z', '--links', '-r', '-R', '--safe-links'],
        ),
    ],
    ids=[
        'push-unknown',
        'push-linux',
        'push-macos',
        'push-macos-wrapper',
        'pull-unknown',
        'pull-linux',
        'pull-macos',
    ],
)
def test_transfer_options_adjusted_for(
    options: TransferOptions, facts: GuestFacts, pushing: bool, expected: list[str]
) -> None:
    assert options.adjusted_for(facts, pushing=pushing).to_rsync() == expected


@pytest.mark.parametrize(
    ('options', 'facts', 'pushing', 'expected_remote', 'protected'),
    [
        (
            None,
            GuestFacts(in_sync=True, has_rsync=True, has_openrsync=True, is_darwin=True),
            True,
            "root@bar:'/var/tmp/work dir/'",
            False,
        ),
        (
            None,
            GuestFacts(in_sync=True, has_rsync=True, has_openrsync=False, is_darwin=False),
            True,
            'root@bar:/var/tmp/work dir/',
            True,
        ),
        (
            # Callers that never set `protect_args`, like the artifact file provider.
            TransferOptions(compress=True),
            GuestFacts(in_sync=True, has_rsync=True, has_openrsync=False, is_darwin=False),
            True,
            "root@bar:'/var/tmp/work dir'",
            False,
        ),
        (
            None,
            GuestFacts(in_sync=True, has_rsync=True, has_openrsync=True, is_darwin=True),
            False,
            "root@bar:'/var/tmp/work dir'",
            False,
        ),
    ],
    ids=['push-macos', 'push-linux', 'push-linux-unprotected', 'pull-macos'],
)
def test_transfer_remote_path(
    root_logger: Logger,
    monkeypatch: _pytest.monkeypatch.MonkeyPatch,
    options: Optional[TransferOptions],
    facts: GuestFacts,
    pushing: bool,
    expected_remote: str,
    protected: bool,
) -> None:
    guest = _ssh_guest(root_logger)
    guest.facts = facts

    run_guest_command = MagicMock()

    monkeypatch.setattr(guest, '_assert_ssh_master_process', MagicMock())
    monkeypatch.setattr(guest, '_run_guest_command', run_guest_command)

    if pushing:
        guest.push(
            source=Path('/tmp/source'), destination=Path('/var/tmp/work dir'), options=options
        )
    else:
        monkeypatch.setattr(guest, 'tmpdir', MagicMock())
        guest.pull(
            source=Path('/var/tmp/work dir'),
            destination=Path('/tmp/destination'),
            options=options,
        )

    command = run_guest_command.call_args.args[0].to_popen()

    assert command[0] == 'rsync'
    assert command[-1 if pushing else -2] == expected_remote
    assert ('-s' in command) is protected
    # A quoted path must reach the remote shell quoted; rsync 3.2.4 and later escape it otherwise.
    environment = run_guest_command.call_args.kwargs['environment']
    assert (environment is None) is protected
    if not protected:
        assert environment == Environment({'RSYNC_OLD_ARGS': EnvVarValue('1')})
    # openrsync accepts the option as the receiver only.
    assert ('--no-implied-dirs' in command) is (pushing and facts.is_darwin is True)


@pytest.mark.parametrize(
    ('method', 'args', 'options', 'expected'),
    [
        (
            'install',
            (Package('flock'), FileSystemPath('/usr/bin/flock')),
            None,
            f'{BREW} install flock flock',
        ),
        (
            'install',
            (Package('flock'),),
            Options(skip_missing=True),
            f'{BREW} install flock || /bin/true',
        ),
        ('reinstall', (Package('bash'),), None, f'{BREW} reinstall bash'),
        ('refresh_metadata', (), None, f'{BREW} update'),
        (
            'check_presence',
            (Package('rsync'), FileSystemPath('/usr/bin/python3')),
            None,
            f'{BREW} list --versions rsync python',
        ),
        ('enable_repo', ('homebrew/core',), None, PrepareError),
        ('disable_repo', ('homebrew/core',), None, PrepareError),
        ('install', (PackageUrl('https://example.com/flock.rb'),), None, PrepareError),
        ('install', (FileSystemPath('/usr/bin/unknown-tool'),), None, GeneralError),
        ('install_debuginfo', (Package('flock'),), None, GeneralError),
        (
            'install',
            (Package('flock'),),
            Options(excluded_packages=[Package('bash')]),
            PrepareError,
        ),
        (
            'reinstall',
            (Package('flock'),),
            Options(excluded_packages=[Package('bash')]),
            PrepareError,
        ),
    ],
    ids=[
        'install',
        'install-skip-missing',
        'reinstall',
        'refresh-metadata',
        'check-presence',
        'enable-repo',
        'disable-repo',
        'install-url',
        'install-unknown-path',
        'install-debuginfo',
        'install-excluded',
        'reinstall-excluded',
    ],
)
def test_homebrew_engine(
    root_logger: Logger,
    method: str,
    args: tuple[object, ...],
    options: Optional[Options],
    expected: Union[str, type[Exception]],
) -> None:
    engine = HomebrewEngine(guest=_homebrew_guest(), logger=root_logger)
    kwargs = {} if options is None else {'options': options}

    if isinstance(expected, str):
        assert str(getattr(engine, method)(*args, **kwargs)) == expected

    else:
        with pytest.raises(expected):
            getattr(engine, method)(*args, **kwargs)


@pytest.mark.parametrize('method', ['install_debuginfo', 'install_local'])
def test_homebrew_unsupported(root_logger: Logger, method: str) -> None:
    manager = Homebrew(guest=_homebrew_guest(), logger=root_logger)

    with pytest.raises(PrepareError):
        getattr(manager, method)(Package('flock'))


def test_homebrew_refuses_root(root_logger: Logger) -> None:
    with pytest.raises(GeneralError, match='does not run as root'):
        Homebrew(guest=_homebrew_guest(is_superuser=True), logger=root_logger)


def test_homebrew_check_presence(root_logger: Logger) -> None:
    guest = _homebrew_guest()
    guest.execute.side_effect = RunError(
        'failed',
        Command('brew'),
        1,
        stdout='flock 0.4.0\npython@3.14 3.14.7\n',
        stderr='Error: No such keg: /opt/homebrew/Cellar/rsync\n',
    )

    manager = Homebrew(guest=guest, logger=root_logger)

    presence = manager.check_presence(
        FileSystemPath('/usr/bin/flock'),
        Package('rsync'),
        Package('bash'),
        FileSystemPath('/usr/bin/python3'),
        Package('python@3.13'),
    )

    assert presence == {
        FileSystemPath('/usr/bin/flock'): True,
        Package('rsync'): False,
        Package('bash'): False,
        FileSystemPath('/usr/bin/python3'): True,
        Package('python@3.13'): False,
    }


@pytest.mark.parametrize(
    ('output', 'expected'),
    [
        (CommandOutput(stdout=None, stderr=''), GeneralError),
        (CommandOutput(stdout='flock 0.4.0\n', stderr=None), {Package('flock'): True}),
    ],
    ids=['no-stdout', 'no-stderr'],
)
def test_homebrew_check_presence_without_output(
    root_logger: Logger,
    output: CommandOutput,
    expected: Union[dict[Installable, bool], type[Exception]],
) -> None:
    guest = _homebrew_guest()
    guest.execute.return_value = output

    manager = Homebrew(guest=guest, logger=root_logger)

    # Only the listing on stdout is read, stderr may be missing.
    if isinstance(expected, dict):
        assert manager.check_presence(Package('flock')) == expected

    else:
        with pytest.raises(expected, match='no output'):
            manager.check_presence(Package('flock'))


def test_homebrew_install_checks_presence_first(root_logger: Logger) -> None:
    guest = _homebrew_guest()
    guest.execute.side_effect = [
        CommandOutput(stdout='flock 0.4.0\n', stderr=''),
        CommandOutput(stdout='', stderr=''),
    ]

    manager = Homebrew(guest=guest, logger=root_logger)

    manager.install(Package('flock'), Package('rsync'), options=Options(check_first=True))

    assert [str(call.args[0]) for call in guest.execute.call_args_list] == [
        f'{BREW} list --versions flock rsync',
        f'{BREW} install rsync',
    ]


def test_homebrew_failed_installation_pattern(root_logger: Logger) -> None:
    manager = Homebrew(guest=_homebrew_guest(), logger=root_logger)

    output = (
        'Warning: No available formula with the name "no-such-formula-zz-9f3a".\n'
        'Error: No formulae or casks found for no-such-formula-zz-9f3a.\n'
    )

    assert list(manager.extract_package_name_from_package_manager_output(output)) == [
        'no-such-formula-zz-9f3a'
    ]


def test_homebrew_probe_command() -> None:
    assert (
        str(Homebrew.probe_command)
        == "/bin/bash -c 'test -x /opt/homebrew/bin/brew || test -x /usr/local/bin/brew'"
    )


def test_homebrew_probe_priority() -> None:
    # Probed after the package managers a Linux guest would have next to Homebrew.
    assert Homebrew.probe_priority < min(Apk.probe_priority, Apt.probe_priority)


@pytest.mark.parametrize(
    ('is_darwin', 'expected_command'),
    [
        (
            True,
            'chmod +a "everyone allow read,execute,file_inherit,directory_inherit,only_inherit"',
        ),
        (False, 'setfacl -d -m o:rX'),
    ],
    ids=['macos', 'linux'],
)
def test_setup_become_acl(
    root_logger: Logger,
    monkeypatch: _pytest.monkeypatch.MonkeyPatch,
    is_darwin: bool,
    expected_command: str,
) -> None:
    guest = _ssh_guest(root_logger, become=True)
    guest.facts = GuestFacts(in_sync=True, is_superuser=False, is_darwin=is_darwin)

    package_manager = MagicMock()
    execute = MagicMock()

    monkeypatch.setattr(GuestSsh, 'package_manager', property(lambda _: package_manager))
    monkeypatch.setattr(guest, 'install_scripts', MagicMock())
    monkeypatch.setattr(guest, 'execute', execute)

    guest.setup()

    script = str(execute.call_args.args[0])
    workdir_root = effective_workdir_root()

    assert f'mkdir -p {workdir_root}' in script
    assert f'{expected_command} {workdir_root}' in script

    if is_darwin:
        package_manager.install.assert_not_called()
    else:
        package_manager.install.assert_called_once_with(FileSystemPath('/usr/bin/setfacl'))


@pytest.mark.parametrize(
    ('dry_run', 'is_superuser', 'become'),
    [(True, False, True), (False, True, True), (False, False, False)],
    ids=['dry-run', 'superuser', 'no-become'],
)
def test_setup_without_acl(
    root_logger: Logger,
    monkeypatch: _pytest.monkeypatch.MonkeyPatch,
    dry_run: bool,
    is_superuser: bool,
    become: bool,
) -> None:
    guest = _ssh_guest(root_logger, become=become, dry_run=dry_run)
    guest.facts = GuestFacts(in_sync=True, is_superuser=is_superuser, is_darwin=True)

    package_manager = MagicMock()
    execute = MagicMock()

    monkeypatch.setattr(GuestSsh, 'package_manager', property(lambda _: package_manager))
    monkeypatch.setattr(guest, 'install_scripts', MagicMock())
    monkeypatch.setattr(guest, 'execute', execute)

    guest.setup()

    execute.assert_not_called()
    package_manager.install.assert_not_called()


@pytest.mark.parametrize(
    ('with_interactive', 'with_tty', 'expected_command'),
    [
        (False, False, './inner.sh </dev/null 2>&1 | cat'),
        (False, True, './inner.sh 2>&1'),
        (True, False, './inner.sh'),
    ],
    ids=['no-tty', 'tty', 'interactive'],
)
@pytest.mark.parametrize(
    ('is_darwin', 'become', 'is_superuser', 'expected_path'),
    [
        (True, False, False, f'export PATH={HOMEBREW_PREFIXES_PATH}:${{PATH}}'),
        (True, False, True, f'export PATH={HOMEBREW_PREFIXES_PATH}:${{PATH}}'),
        (True, True, False, f'export PATH=${{PATH}}:{HOMEBREW_PREFIXES_PATH}'),
        (True, True, True, f'export PATH={HOMEBREW_PREFIXES_PATH}:${{PATH}}'),
        (False, False, False, None),
        (False, True, True, None),
    ],
    ids=[
        'macos',
        'macos-superuser',
        'macos-become',
        'macos-become-superuser',
        'linux',
        'linux-become-superuser',
    ],
)
def test_outer_wrapper(
    with_interactive: bool,
    with_tty: bool,
    expected_command: str,
    is_darwin: bool,
    become: bool,
    is_superuser: bool,
    expected_path: Optional[str],
) -> None:
    guest = MagicMock()
    guest.facts.is_darwin = is_darwin
    guest.facts.is_superuser = is_superuser
    guest.facts.sudo_prefix = '' if is_superuser else 'sudo'
    guest.become = become
    guest.scripts_path = '/usr/local/bin'

    # The prefixes are the template's own, not a render variable a caller could forget.
    wrapper = OUTER_WRAPPER_TEMPLATE.render(
        GUEST=guest,
        COMMAND=ShellScript('./inner.sh'),
        BEFORE_MESSAGE='before',
        AFTER_MESSAGE=None,
        WITH_INTERACTIVE=with_interactive,
        WITH_TTY=with_tty,
    )

    echo = (
        'echo "before" > /dev/kmsg'
        if is_superuser
        else 'sudo bash -c "echo \\"before\\" > /dev/kmsg"'
    )

    assert f'if [ -e /dev/kmsg ]; then\n    {echo}\nfi' in wrapper

    # The wrapper has to run under bash 3.2, hence `2>&1 |` rather than `|&`.
    assert '|&' not in wrapper
    assert f'\n{expected_command}\n_exit_code="$?"' in wrapper

    if expected_path is None:
        assert HOMEBREW_PREFIXES[0] not in wrapper

    else:
        assert wrapper.index(expected_path) < wrapper.index('flock ')


def test_execute_resets_rsync_facts(
    root_logger: Logger, monkeypatch: _pytest.monkeypatch.MonkeyPatch
) -> None:
    guest = MagicMock()
    guest.facts = GuestFacts(in_sync=True, has_rsync=True, has_openrsync=True, is_darwin=True)

    invocation = MagicMock()
    invocation.guest = guest
    invocation.pidfile.create_wrappers.return_value = (Path('inner.sh'), Path('outer.sh'))
    invocation.invoke_test.return_value = CommandOutput(stdout='', stderr='')

    plugin = MagicMock()
    plugin.data.interactive = False
    plugin.data.ignore_duration = True

    # The facts as seen by each pull that follows the test.
    pulled: list[tuple[Optional[bool], Optional[bool]]] = []
    plugin._post_action_pull.side_effect = lambda **kwargs: pulled.append(
        (guest.facts.has_rsync, guest.facts.has_openrsync)
    )

    monkeypatch.setattr(tmt.steps, 'Topology', MagicMock())
    monkeypatch.setattr(tmt.steps, 'GuestTopology', MagicMock())

    ExecuteInternal.execute(plugin, invocation=invocation, logger=root_logger)

    # A test may install or remove rsync, the pulls that follow have to ask again.
    assert pulled == [(None, None), (None, None)]
    assert guest.facts.is_darwin is True
