import os
import re
from typing import Optional
from unittest.mock import MagicMock

import pytest

import tmt.log
from tmt.guest import (
    GuestSsh,
    GuestSshData,
    _socket_path_hash,
    _socket_path_trivial,
)
from tmt.steps.provision import Provision
from tmt.utils import Path


@pytest.mark.parametrize(
    ('socket_dir', 'limit_size', 'expected'),
    [
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


def test_ssh_does_not_share_socket_between_guests(root_logger, tmppath) -> None:
    """SSH master sockets must be unique for multiple guests in one plan."""
    provision = MagicMock(spec=Provision)
    provision.run_workdir = tmppath
    guests = {
        name: GuestSsh(
            logger=root_logger,
            parent=provision,
            name=name,
            data=GuestSshData(primary_address=address),
        )
        for name, address in (
            ('guest-one', '192.0.2.1'),
            ('guest-two', '192.0.2.2'),
        )
    }
    socket_paths = {name: guest._ssh_master_socket_path for name, guest in guests.items()}
    assert len(set(socket_paths.values())) == len(guests)
