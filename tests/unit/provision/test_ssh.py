import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from unittest.mock import MagicMock

import pytest

import tmt.log
from tmt.guest import (
    SSH_MASTER_SOCKET_LENGTH_LIMIT,
    GuestSsh,
    GuestSshData,
    _socket_path_hash,
    _socket_path_trivial,
)
from tmt.utils import Path


@pytest.mark.parametrize(
    ('socket_dir', 'limit_size', 'expected'),
    [
        (
            Path('/' + 'é' * 34),
            True,
            None,
        ),
        (
            Path('/tmp'),
            True,
            Path('/tmp/dummy-id.socket'),
        ),
        (
            Path('/very/log/socket/dir/which/is/almost/over/the/limit/but/just/and/soo'),
            True,
            None,
        ),
        (
            Path('/very/log/socket/dir/which/is/over/the/limit/by/itself/and/does/not/need'),
            True,
            None,
        ),
        (
            Path('/very/log/socket/dir/which/is/almost/over/the/limit/but/just/and/soo'),
            False,
            Path(
                '/very/log/socket/dir/which/is/almost/over/the/limit/but/just/and/soo/dummy-id.socket'
            ),
        ),
        (
            Path('/very/log/socket/dir/which/is/over/the/limit/by/itself/and/does/not/need'),
            False,
            Path(
                '/very/log/socket/dir/which/is/over/the/limit/by/itself/and/does/not/need/dummy-id.socket'
            ),
        ),
    ],
)
def test_socket_path_trivial(
    socket_dir: Path, limit_size: bool, expected: Optional[Path], root_logger: tmt.log.Logger
) -> None:
    actual = _socket_path_trivial(
        socket_dir=socket_dir, guest_id='dummy-id', limit_size=limit_size, logger=root_logger
    )

    if expected is None:
        assert actual is expected

    else:
        assert str(actual) == str(expected)


@pytest.mark.parametrize(
    ('socket_dir', 'limit_size', 'expected'),
    [
        (Path('/tmp'), True, r'/tmp/[a-z0-9]{4}.socket'),
        (Path('/' + 'é' * 36), True, None),
        (
            Path('/very/log/socket/dir/which/is/almost/over/the/limit/but/just/and/soo'),
            True,
            r'/very/log/socket/dir/which/is/almost/over/the/limit/but/just/and/soo/[a-z0-9]{4}.socket',
        ),
        (
            Path('/very/log/socket/dir/which/is/over/the/limit/by/itself/and/does/not/need'),
            True,
            None,
        ),
        (
            Path('/very/log/socket/dir/which/is/almost/over/the/limit/but/just/and/soo'),
            False,
            r'/very/log/socket/dir/which/is/almost/over/the/limit/but/just/and/soo/[a-z0-9]{4}.socket',
        ),
        (
            Path('/very/log/socket/dir/which/is/over/the/limit/by/itself/and/does/not/need'),
            False,
            r'/very/log/socket/dir/which/is/over/the/limit/by/itself/and/does/not/need/[a-z0-9]{4}.socket',
        ),
    ],
)
def test_socket_path_hash(
    socket_dir: Path,
    limit_size: bool,
    expected: Optional[str],
    monkeypatch,
    root_logger: tmt.log.Logger,
) -> None:
    monkeypatch.setattr(os, 'open', MagicMock(name='<mock>os.open'))
    monkeypatch.setattr(os, 'close', MagicMock(name='<mock>os.close'))

    actual = _socket_path_hash(
        socket_dir=socket_dir, guest_id='dummy-id', limit_size=limit_size, logger=root_logger
    )

    if expected is None:
        assert actual is expected

    else:
        assert re.match(expected, str(actual))


def test_socket_path_hash_conflict(monkeypatch, root_logger: tmt.log.Logger) -> None:
    monkeypatch.setattr(os, 'close', MagicMock(name='<mock>os.close'))

    socket_dir = Path('/tmp')

    # First, "create" a socket for the first guest.
    monkeypatch.setattr(os, 'open', MagicMock(name='<mock>os.open'))

    actual1 = _socket_path_hash(socket_dir=socket_dir, guest_id='dummy-id', logger=root_logger)

    # Second, simulate "file exists" error to inject the conflict. We
    # did not create the file, just pretending via capturing `os.open`.
    def _raise_but_once(filepath: Path, **kwargs):
        if str(filepath).replace('.reservation', '') == str(actual1):
            raise FileExistsError

        return MagicMock()

    monkeypatch.setattr(os, 'open', MagicMock(name='<mock>os.open', side_effect=_raise_but_once))

    actual2 = _socket_path_hash(socket_dir=socket_dir, guest_id='dummy-id', logger=root_logger)

    assert re.match(r'/tmp/[a-z0-9]{4}.socket', str(actual1))
    assert re.match(r'/tmp/[a-z0-9]{5}.socket', str(actual2))


@pytest.fixture
def ssh_guest(monkeypatch: pytest.MonkeyPatch, root_logger: tmt.log.Logger) -> Iterator[GuestSsh]:
    """Create a guest with a short workdir, without opening a connection."""

    with tempfile.TemporaryDirectory(prefix='tmt-unit-', dir='/tmp') as directory:
        monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: Path(directory)))
        guest = GuestSsh(
            data=GuestSshData(primary_address='127.0.0.1', user='root'), logger=root_logger
        )

        yield guest

        if '_ssh_master_socket_path' in guest.__dict__:
            guest._flush_ssh_master_socket_path()


def test_socket_path_in_workdir(ssh_guest: GuestSsh) -> None:
    """Keep the readable socket path for short workdirs."""

    assert ssh_guest._ssh_master_socket_path == (
        ssh_guest.run_workdir / 'ssh-sockets/127.0.0.1-root.socket'
    )


@pytest.mark.parametrize('dirname', ['long-' * 30, 'é' * 40])
def test_socket_path_temporary(
    dirname: str, ssh_guest: GuestSsh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Long workdirs use a short, private directory and an actual UNIX socket."""

    workdir = ssh_guest.run_workdir / dirname
    monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: workdir))
    monkeypatch.setenv('TMPDIR', str(workdir))

    path = ssh_guest._ssh_master_socket_path

    assert ssh_guest.is_ssh_multiplexing_enabled
    assert len(os.fsencode(path)) < SSH_MASTER_SOCKET_LENGTH_LIMIT
    assert not path.is_relative_to(workdir)
    assert path.parent.stat().st_uid == os.getuid()
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert f'-S{path}' in ssh_guest._ssh_options.to_popen()
    assert ssh_guest._ssh_master_socket_path == path

    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        assert path.is_socket()

    ssh_guest._flush_ssh_master_socket_path()
    assert not path.parent.exists()


@pytest.mark.parametrize(
    ('address', 'port', 'user'),
    [('127.0.0.1', None, 'root'), ('127.0.0.2', None, 'root'), ('127.0.0.1', 2222, 'other')],
)
def test_socket_path_temporary_isolation(
    address: str,
    port: Optional[int],
    user: str,
    ssh_guest: GuestSsh,
    monkeypatch: pytest.MonkeyPatch,
    root_logger: tmt.log.Logger,
) -> None:
    """Guest instances, including resumed runs, never share fallback sockets."""

    workdir = ssh_guest.run_workdir / ('long-' * 30)
    monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: workdir))
    other = GuestSsh(
        data=GuestSshData(primary_address=address, port=port, user=user), logger=root_logger
    )

    path = ssh_guest._ssh_master_socket_path
    other_path = other._ssh_master_socket_path

    try:
        assert path.parent != other_path.parent
        ssh_guest._flush_ssh_master_socket_path()
        assert other_path.parent.is_dir()

        # A reconnect must allocate a fresh path without touching the other guest.
        assert ssh_guest._ssh_master_socket_path not in (path, other_path)

    finally:
        other._flush_ssh_master_socket_path()


def test_socket_path_temporary_second_root(
    ssh_guest: GuestSsh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Try another short temporary root if the first one is unavailable."""

    workdir = ssh_guest.run_workdir / ('long-' * 30)
    monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: workdir))
    original = tempfile.TemporaryDirectory

    def create_directory(**kwargs: str) -> 'tempfile.TemporaryDirectory[str]':
        if kwargs['dir'] == '/tmp':
            raise PermissionError('Unavailable temporary directory')

        return original(**kwargs)

    monkeypatch.setattr(tempfile, 'TemporaryDirectory', create_directory)

    assert ssh_guest.is_ssh_multiplexing_enabled
    assert ssh_guest._ssh_master_socket_path.parent.parent == Path('/var/tmp')


def test_socket_path_temporary_concurrent(
    ssh_guest: GuestSsh, monkeypatch: pytest.MonkeyPatch, root_logger: tmt.log.Logger
) -> None:
    """Concurrent guest instances reserve distinct private directories."""

    workdir = ssh_guest.run_workdir / ('long-' * 30)
    monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: workdir))
    guests = [
        GuestSsh(data=GuestSshData(primary_address='127.0.0.1', user='root'), logger=root_logger)
        for _ in range(8)
    ]

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            paths = list(executor.map(lambda guest: guest._ssh_master_socket_path, guests))

        assert len({path.parent for path in paths}) == len(guests)
        assert all(path.parent.is_dir() for path in paths)

    finally:
        for guest in guests:
            guest._flush_ssh_master_socket_path()


def test_socket_path_temporary_failure(
    ssh_guest: GuestSsh,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep running without multiplexing if no private directory can be created."""

    workdir = ssh_guest.run_workdir / ('long-' * 30)
    monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: workdir))
    create_directory = MagicMock(side_effect=PermissionError('Unavailable temporary directory'))
    monkeypatch.setattr(tempfile, 'TemporaryDirectory', create_directory)

    assert not ssh_guest.is_ssh_multiplexing_enabled
    assert 'SSH multiplexing will not be used' in caplog.text
    assert create_directory.call_count == 2
    assert not any(option.startswith('-S') for option in ssh_guest._ssh_options.to_popen())


def test_socket_path_temporary_master_cleanup(
    ssh_guest: GuestSsh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stopping a master removes its private directory and resets path validation."""

    workdir = ssh_guest.run_workdir / ('long-' * 30)
    monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: workdir))
    assert ssh_guest.is_ssh_multiplexing_enabled
    path = ssh_guest._ssh_master_socket_path
    process = MagicMock()
    ssh_guest._ssh_master_process = process

    ssh_guest._cleanup_ssh_master_process()

    process.send_signal.assert_called_once()
    process.wait.assert_called_once_with(timeout=3)
    assert ssh_guest._ssh_master_process is None
    assert not path.parent.exists()

    monkeypatch.setattr(
        tempfile, 'TemporaryDirectory', MagicMock(side_effect=PermissionError('Unavailable'))
    )
    assert not ssh_guest.is_ssh_multiplexing_enabled


@pytest.mark.parametrize('termination', ['normal', 'abrupt'])
def test_socket_path_temporary_exit(
    termination: str, tmppath: Path, ssh_guest: GuestSsh, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clean up on shutdown and never reuse directories left by a killed process."""

    script = """
import os
import sys
from tmt.guest import GuestSsh, GuestSshData
from tmt.log import Logger
from tmt.utils import Path

GuestSsh.run_workdir = property(lambda self: Path(sys.argv[1]))
guest = GuestSsh(
    data=GuestSshData(primary_address='127.0.0.1', user='root'), logger=Logger.create()
)
print(guest._ssh_master_socket_path, flush=True)
if sys.argv[2] == 'abrupt':
    os._exit(0)
"""
    workdir = tmppath / ('long-' * 30)
    result = subprocess.run(
        [sys.executable, '-c', script, str(workdir), termination],
        check=True,
        capture_output=True,
        text=True,
    )
    path = Path(result.stdout.strip())
    assert path.name == 'master.socket'

    if termination == 'normal':
        assert not path.parent.exists()

    else:
        try:
            assert path.parent.is_dir()
            monkeypatch.setattr(GuestSsh, 'run_workdir', property(lambda self: workdir))
            assert ssh_guest._ssh_master_socket_path.parent != path.parent

        finally:
            shutil.rmtree(path.parent)
