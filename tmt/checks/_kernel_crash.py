"""
Guest-side kdump inspection using only the Python standard library.

Executed as a script on the guest; this module must not import tmt. NFS
targets are mounted read-only for inspection and released before returning.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path  # noqa: TID251
from typing import Any, Optional

BOOT_ID: Path = Path('/proc/sys/kernel/random/boot_id')
CRASH_LOADED: Path = Path('/sys/kernel/kexec_crash_loaded')
KDUMP_CONFIG: Path = Path('/etc/kdump.conf')
KMSG: Path = Path('/dev/kmsg')
LOG_NAMES: tuple[str, ...] = ('vmcore-dmesg.txt', 'kexec-dmesg.log')
MAX_LOG_BYTES: int = 8 * 1024 * 1024
DUMP_NAME: re.Pattern[str] = re.compile(r'\d{4}-\d\d-\d\d-\d\d:\d\d:\d\d$')


def _read(path: Path) -> str:
    """Read an optional system file."""

    try:
        return path.read_text().strip()
    except OSError:
        return ''


def _run(*args: str) -> str:
    """Bound commands that may access an unavailable dump target."""

    return subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=20
    ).stdout.strip()


@contextmanager
def dump_roots(
    override: Optional[str], errors: list[str]
) -> Generator[list[tuple[Path, str]], None, None]:
    """Resolve local, mounted filesystem and NFS targets from kdump.conf."""

    if override:
        yield [(Path(override), override)]
        return

    options: dict[str, str] = {}
    for line in _read(KDUMP_CONFIG).splitlines():
        fields = line.partition('#')[0].split(maxsplit=1)
        if len(fields) == 2:
            options[fields[0]] = fields[1]

    path = options.get('path', '/var/crash')
    roots: list[tuple[Path, str]] = []
    mountpoint: Optional[str] = None
    mounted = False

    try:
        targets = {'nfs', 'ext2', 'ext3', 'ext4', 'xfs', 'btrfs'} & options.keys()
        if targets:
            target = min(targets)
            source = options[target]
            location = f'{source}/{path.lstrip("/")}'
            try:
                existing = _run(
                    'findmnt',
                    '--noheadings',
                    '--first-only',
                    '--output',
                    'TARGET',
                    '--source',
                    source,
                )
            except (OSError, subprocess.SubprocessError):
                existing = ''

            if existing:
                roots.append((Path(existing) / path.lstrip('/'), location))
            elif target == 'nfs':
                mountpoint = tempfile.mkdtemp(prefix='tmt-kernel-crash-', dir='/var/tmp')
                _run(
                    'mount',
                    '-t',
                    'nfs',
                    '-o',
                    'ro,soft,timeo=50,retrans=2,retry=0',
                    source,
                    mountpoint,
                )
                mounted = True
                roots.append((Path(mountpoint) / path.lstrip('/'), location))
            else:
                errors.append(f'kdump target {source} is not mounted')

        elif {'ssh', 'raw'} & options.keys():
            errors.append(
                'kdump SSH/raw target cannot be inspected; use dump-path for a mounted copy'
            )
        else:
            roots.append((Path(path), path))

    except (OSError, subprocess.SubprocessError) as error:
        errors.append(f'Cannot access kdump target: {error}')

    if options.get('failure_action') == 'dump_to_rootfs':
        roots.append((Path(path), path))

    try:
        yield roots
    finally:
        if mountpoint:
            if mounted:
                try:
                    _run('umount', mountpoint)
                except (OSError, subprocess.SubprocessError):
                    try:
                        _run('umount', '-l', mountpoint)
                    except (OSError, subprocess.SubprocessError) as error:
                        errors.append(f'Cannot release kdump mount: {error}')
            with suppress(OSError):
                os.rmdir(mountpoint)


def inspect(options: dict[str, Any]) -> dict[str, Any]:
    """Record boot identity and dump inventory, optionally collecting new logs."""

    errors: list[str] = []
    snapshot: dict[str, Any] = {
        'boot_id': _read(BOOT_ID),
        'timestamp': time.time(),
        'kdump_loaded': _read(CRASH_LOADED) == '1',
        'dumps': [],
        'errors': errors,
    }
    known = set(options.get('known', []))
    since = options.get('since')

    with dump_roots(options.get('dump_path'), errors) as roots:
        for root, location in roots:
            try:
                if not root.exists():
                    continue
                for entry in sorted(root.iterdir()):
                    if not DUMP_NAME.search(entry.name) or not entry.is_dir():
                        continue
                    identity = f'{location.rstrip("/")}/{entry.name}'
                    modified = entry.stat().st_mtime
                    dump: dict[str, Any] = {'path': identity, 'timestamp': modified}
                    if since is not None:
                        if identity in known or modified < since - 60:
                            continue
                        dump['has_vmcore'] = (entry / 'vmcore').is_file()
                        logs: dict[str, str] = {}
                        for name in LOG_NAMES:
                            logfile = entry / name
                            if logfile.is_file():
                                with logfile.open('rb') as stream:
                                    data = stream.read(MAX_LOG_BYTES + 1)
                                logs[name] = data[:MAX_LOG_BYTES].decode(errors='replace')
                                if len(data) > MAX_LOG_BYTES:
                                    errors.append(
                                        f'{identity}/{name} truncated at {MAX_LOG_BYTES} bytes'
                                    )
                        dump['logs'] = logs
                        if not dump['has_vmcore'] and not logs:
                            continue
                    snapshot['dumps'].append(dump)
            except OSError as error:
                errors.append(f'Cannot inspect {location}: {error}')

    snapshot['inventory_errors'] = errors[:]
    if marker := options.get('marker'):
        try:
            # Retain boot and invocation identity even if the test name is long.
            KMSG.write_text(f'<5>tmt: boot {snapshot["boot_id"]} invocation {marker}\n')
        except OSError as error:
            errors.append(f'Cannot write kernel invocation marker: {error}')

    return snapshot


def copy_vmcore(options: dict[str, Any]) -> dict[str, Any]:
    """Stage an explicitly requested vmcore on the guest for bounded transfer."""

    errors: list[str] = []
    with dump_roots(options.get('dump_path'), errors) as roots:
        for root, location in roots:
            name = options['path'].removeprefix(f'{location.rstrip("/")}/')
            if name == options['path'] or '/' in name or name in ('.', '..'):
                continue
            destination = Path(options['destination'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.touch(mode=0o600)
            destination.chmod(0o600)
            shutil.copyfile(root / name / 'vmcore', destination)
            # The guest helper cannot depend on tmt's Environment class.
            environment = os.environ  # noqa: TID251
            if uid := environment.get('SUDO_UID'):
                os.chown(destination, int(uid), int(environment.get('SUDO_GID', uid)))
            return {'errors': errors}

    raise OSError(f'Cannot access vmcore at {options["path"]}: {errors}')


def _timeout(signum: int, frame: Any) -> None:
    """Unwind mount contexts when the enclosing timeout terminates inspection."""

    raise TimeoutError('Kdump inspection timed out')


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _timeout)
    request = json.loads(sys.argv[1])
    response = copy_vmcore(request) if request.get('action') == 'vmcore' else inspect(request)
    print(json.dumps(response))
