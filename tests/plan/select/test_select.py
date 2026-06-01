import re
from typing import TYPE_CHECKING

import pytest

from tmt.utils import GeneralError, Path

if TYPE_CHECKING:
    from tests import RunTmt


def test_ls(run_tmt: 'RunTmt') -> None:
    result = run_tmt('plan', 'ls')

    assert re.search(r'(?m)^/plans/features/core$', result.stdout)
    assert re.search(r'(?m)^/plans/features/basic$', result.stdout)
    assert not result.stderr


def test_ls_select_by_name(run_tmt: 'RunTmt') -> None:
    result = run_tmt('plan', 'ls', 'core')

    assert re.search(r'(?m)^/plans/features/core$', result.stdout)
    assert not re.search(r'(?m)^/plans/features/basic$', result.stdout)
    assert not result.stderr


def test_ls_select_by_invalid_name(run_tmt: 'RunTmt') -> None:
    result = run_tmt('plan', 'ls', 'non-existent')

    assert not result.stdout
    assert not result.stderr


@pytest.mark.parametrize('exclude_option', ['-x', '--exclude'])
def test_ls_select_by_exclude(run_tmt: 'RunTmt', tmpdir: Path, exclude_option: str) -> None:
    result = run_tmt('plan', 'ls', exclude_option, 'core')

    assert not re.search(r'(?m)^/plans/features/core$', result.stdout)
    assert re.search(r'(?m)^/plans/features/basic$', result.stdout)


def test_show(run_tmt: 'RunTmt') -> None:
    result = run_tmt('plan', 'show')

    assert re.search(r'(?m)^/plans/features/core$', result.stdout)
    assert re.search(r'(?m)^/plans/features/basic$', result.stdout)
    assert not result.stderr


@pytest.mark.parametrize('filter_option', ['-f', '--filter'])
def test_show_with_filter(run_tmt: 'RunTmt', filter_option: str) -> None:
    result = run_tmt('plan', 'show', filter_option, 'description:.*fast.*')

    assert re.search(r'(?m)^/plans/features/core$', result.stdout)
    assert not re.search(r'(?m)^/plans/features/basic$', result.stdout)
    assert not result.stderr


@pytest.mark.parametrize('name_option', ['-n', '--name'])
def test_run_with_name(run_tmt: 'RunTmt', tmpdir: Path, name_option: str) -> None:
    result = run_tmt('run', '-i', tmpdir, 'discover', 'plan', name_option, 'core')

    assert not result.stdout
    assert re.search(r'(?m)^/plans/features/core$', result.stderr)


@pytest.mark.parametrize('name_option', ['-n', '--name'])
def test_run_with_invalid_name(run_tmt: 'RunTmt', tmpdir: Path, name_option: str) -> None:
    with pytest.raises(GeneralError, match=r'(?m)^No plans found\.$'):
        run_tmt('run', '-i', tmpdir, 'discover', 'plan', name_option, 'non-existent')
